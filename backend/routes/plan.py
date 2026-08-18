"""/plans 系列。

阶段 3（已接入）：create/list/get/patch 全部落库，不再返 mock 常量。

计划生成（PRD 5.1 MVP 简化版）：
  1. 取用户 active 目标（goalIds 不传则全部 active）
  2. 按 availableMinutes 切分任务：每目标先放一个核心任务（25-40min），
     剩余时间按优先级补第二个任务；单任务时长 20-45min
  3. adaptedFrom：查最近一次 data_sufficient 的 AssessmentSnapshot，
     按 stateLabel 决定 adjustment（reduce_load / maintain / extend）
  4. 同 planDate 已有计划 → 409；regenerate=true → 删旧（连带 plan_tasks）再建
任务调整：PATCH 走真改库，软删除（removed=True）保留反馈信号，userAdjusted 标记。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.assessment import AssessmentSnapshot as AssessmentSnapshotORM
from models.goal import Goal as GoalORM
from models.plan import Plan as PlanORM
from models.plan import PlanTask as PlanTaskORM
from schemas.common import Pagination
from schemas.plan import (
    Plan,
    PlanAdaptation,
    PlanCreate,
    PlanList,
    PlanTask,
    PlanTaskDetail,
    PlanTaskUpdate,
)
from schemas.user import User
from state_calculator import gen_id
from .deps import current_user

router = APIRouter(prefix="/plans", tags=["学习计划"])


# ---------- 任务时长切分 ----------

# PRD 5.1 MVP 边界：任务级规划，颗粒度到「学科+方向+时长」
_MIN_TASK_MINUTES = 20
_MAX_TASK_MINUTES = 45
_DEFAULT_TASK_MINUTES = 30

# 每个学科的任务模板（topic 颗粒度，不含具体题目，PRD 5.1 边界）
_SUBJECT_TOPICS = {
    "math": ["函数与导数 · 巩固", "数列 · 专题", "几何 · 综合训练", "错题回顾"],
    "english": ["阅读理解 · 限时", "完形填空 · 专项", "写作 · 模板练习", "单词复习"],
    "physics": ["力学 · 综合", "电学 · 专题", "实验题 · 训练", "错题回顾"],
    "chemistry": ["化学方程式 · 训练", "有机化学 · 专题", "实验题 · 训练", "错题回顾"],
    "biology": ["遗传 · 专题", "细胞 · 巩固", "实验题 · 训练", "错题回顾"],
    "chinese": ["文言文 · 精读", "现代文 · 阅读", "作文 · 素材积累", "默写巩固"],
    "history": ["通史 · 梳理", "专题 · 训练", "材料题 · 分析", "错题回顾"],
    "geography": ["自然地理 · 专题", "人文地理 · 训练", "图表题 · 分析", "错题回顾"],
    "politics": ["经济 · 专题", "政治 · 训练", "时政 · 分析", "错题回顾"],
    "other": ["综合 · 训练", "错题回顾"],
}


def _pick_topic(subject: str, idx: int) -> str:
    """按学科和序号选 topic，循环回退。"""
    topics = _SUBJECT_TOPICS.get(subject, _SUBJECT_TOPICS["other"])
    return topics[idx % len(topics)]


def _split_tasks(
    available_minutes: int,
    goals: list[GoalORM],
) -> list[dict]:
    """按可用时间和和目标列表生成任务。

    策略（MVP 规则模板，PRD 5.1）：
      - 至少为每个目标生成一个核心任务（25-40min）
      - 剩余时间按目标顺序补第二个任务
      - 单任务时长 20-45min；剩余时间不足以再加新任务则结束
      - priority 从 1 递增
    """
    if not goals:
        return []

    tasks: list[dict] = []
    remaining = available_minutes
    priority = 1

    # 第一轮：每目标一个核心任务
    for goal in goals:
        if remaining < _MIN_TASK_MINUTES:
            break
        # 疲劳状态缩短单任务时长（adaptedFrom 在外层处理，这里按默认）
        task_min = min(_DEFAULT_TASK_MINUTES, remaining, _MAX_TASK_MINUTES)
        if task_min < _MIN_TASK_MINUTES:
            task_min = min(_MIN_TASK_MINUTES, remaining)
        tasks.append({
            "subject": goal.subject,
            "topic": _pick_topic(goal.subject, 0),
            "estimated_minutes": task_min,
            "priority": priority,
            "goal_id": goal.id,
        })
        remaining -= task_min
        priority += 1

    # 第二轮：剩余时间按目标顺序补第二个任务
    if remaining >= _MIN_TASK_MINUTES:
        for goal in goals:
            if remaining < _MIN_TASK_MINUTES:
                break
            task_min = min(_DEFAULT_TASK_MINUTES, remaining, _MAX_TASK_MINUTES)
            tasks.append({
                "subject": goal.subject,
                "topic": _pick_topic(goal.subject, 1),
                "estimated_minutes": task_min,
                "priority": priority,
                "goal_id": goal.id,
            })
            remaining -= task_min
            priority += 1

    return tasks


# ---------- adaptedFrom（强度调整） ----------

# 状态标签 → 调整方向映射（PRD 5.1 第 2 点：状态偏疲劳降强度，高效稳定可提强度）
_STATE_ADJUSTMENT = {
    "fatigue_warning": ("reduce_load", "最近状态偏疲劳，本次总时长下调，单任务时长缩短"),
    "emotion_blocked": ("reduce_load", "情绪受阻，任务量适度下调，优先选熟悉内容巩固"),
    "fluctuating_up": ("maintain", "状态波动上升，保持当前任务量，注意节奏"),
    "efficient_stable": ("maintain", "状态稳定高效，保持当前节奏"),
    "insufficient_data": ("maintain", "数据积累中，按默认强度安排"),
}


def _build_adapted_from(
    db: Session, user_id: str, available_minutes: int
) -> PlanAdaptation | None:
    """查最近一次 data_sufficient 的 AssessmentSnapshot，构造 adaptedFrom。

    新用户无历史数据 → 返回 None（契约允许 adaptedFrom 整体为 null）。
    有快照但状态偏疲劳时，把任务总时长下调到 80%（reduce_load 的具象化）。
    """
    snapshot = db.execute(
        select(AssessmentSnapshotORM)
        .where(
            AssessmentSnapshotORM.user_id == user_id,
            AssessmentSnapshotORM.data_sufficient.is_(True),
        )
        .order_by(
            AssessmentSnapshotORM.computed_at.desc(),
            AssessmentSnapshotORM.id.desc(),
        )
        .limit(1)
    ).scalars().first()
    if snapshot is None:
        return None

    adjustment, note = _STATE_ADJUSTMENT.get(
        snapshot.state_label, ("maintain", "保持当前节奏")
    )
    return PlanAdaptation(
        assessmentId=snapshot.id,
        stateLabel=snapshot.state_label,
        adjustment=adjustment,
        note=note,
    )


# ---------- ORM ↔ Schema ----------

def _orm_task_to_dict(row: PlanTaskORM) -> dict:
    return {
        "taskId": row.id,
        "subject": row.subject,
        "topic": row.topic,
        "estimatedMinutes": row.estimated_minutes,
        "priority": row.priority,
        "status": row.status,
        "goalId": row.goal_id,
    }


def _orm_plan_to_dict(row: PlanORM, tasks: list[PlanTaskORM]) -> dict:
    adapted_from = None
    if row.adapted_from_assessment_id:
        adapted_from = {
            "assessmentId": row.adapted_from_assessment_id,
            "stateLabel": row.adapted_from_state_label,
            "adjustment": row.adapted_from_adjustment,
            "note": row.adapted_from_note,
        }
    return {
        "planId": row.id,
        "planDate": row.plan_date.isoformat(),
        "availableMinutes": row.available_minutes,
        "adaptedFrom": adapted_from,
        "tasks": [_orm_task_to_dict(t) for t in tasks],
        "createdAt": row.created_at.isoformat(),
    }


def _load_plan_tasks(db: Session, plan_id: str) -> list[PlanTaskORM]:
    """按 priority 升序加载该计划下未软删除的任务。"""
    return list(db.execute(
        select(PlanTaskORM)
        .where(
            PlanTaskORM.plan_id == plan_id,
            PlanTaskORM.removed.is_(False),
        )
        .order_by(PlanTaskORM.priority.asc(), PlanTaskORM.id.asc())
    ).scalars().all())


# ---------- 路由 ----------

@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED, summary="生成学习计划 ②")
def create_plan(
    body: PlanCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Plan:
    # 同 planDate 已有计划 → 409；regenerate=true → 删旧（连带 plan_tasks）再建
    existing = db.execute(
        select(PlanORM).where(
            PlanORM.user_id == _user.user_id,
            PlanORM.plan_date == body.plan_date,
        )
    ).scalars().first()

    if existing is not None:
        if not body.regenerate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "STATE_CONFLICT",
                    "message": "当日已存在计划，如需覆盖请传 regenerate=true",
                },
            )
        # 覆盖：删旧计划（plan_tasks 通过 ondelete=CASCADE 连带删除）
        db.delete(existing)
        db.commit()

    # 取目标：goalIds 不传则全部 active
    goal_query = select(GoalORM).where(
        GoalORM.user_id == _user.user_id,
        GoalORM.status == "active",
    )
    if body.goal_ids:
        goal_query = goal_query.where(GoalORM.id.in_(body.goal_ids))
    goals = list(db.execute(goal_query.order_by(GoalORM.created_at.asc())).scalars().all())

    # adaptedFrom：最近一次状态评估（新用户为 None）
    adaptation = _build_adapted_from(db, _user.user_id, body.available_minutes)

    # 疲劳状态把可用时长降到 80%（reduce_load 的具象化）
    effective_minutes = body.available_minutes
    if adaptation and adaptation.adjustment == "reduce_load":
        effective_minutes = max(_MIN_TASK_MINUTES, int(body.available_minutes * 0.8))

    task_dicts = _split_tasks(effective_minutes, goals)

    # P0-1 兜底：无目标（或可用时间不足以放任何任务）时，补一条通用任务，
    # 保证 tasks 至少 1 条，前端推荐（取 tasks[0].topic）永远有内容可填。
    # topic 用可读中文（Jacky 方案A P0-2），subject 用合法枚举 other（P0-3）。
    if not task_dicts:
        task_dicts = [{
            "subject": "other",
            "topic": "自由学习 · 巩固已学",
            "estimated_minutes": min(_DEFAULT_TASK_MINUTES, effective_minutes, _MAX_TASK_MINUTES),
            "priority": 1,
            "goal_id": None,
        }]

    plan_id = gen_id("p")
    plan_row = PlanORM(
        id=plan_id,
        user_id=_user.user_id,
        plan_date=body.plan_date,
        available_minutes=body.available_minutes,  # 原值，便于回看用户当时输入
        adapted_from_assessment_id=adaptation.assessment_id if adaptation else None,
        adapted_from_state_label=adaptation.state_label if adaptation else None,
        adapted_from_adjustment=adaptation.adjustment if adaptation else None,
        adapted_from_note=adaptation.note if adaptation else None,
    )
    db.add(plan_row)

    for t in task_dicts:
        db.add(PlanTaskORM(
            id=gen_id("t"),
            plan_id=plan_id,
            user_id=_user.user_id,
            subject=t["subject"],
            topic=t["topic"],
            estimated_minutes=t["estimated_minutes"],
            priority=t["priority"],
            status="pending",
            goal_id=t["goal_id"],
        ))
    db.commit()
    db.refresh(plan_row)

    tasks = _load_plan_tasks(db, plan_id)
    return Plan.model_validate(_orm_plan_to_dict(plan_row, tasks))


@router.get("", response_model=PlanList, summary="计划列表")
def list_plans(
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> PlanList:
    query = select(PlanORM).where(PlanORM.user_id == _user.user_id)
    if date_from:
        query = query.where(PlanORM.plan_date >= date_from)
    if date_to:
        query = query.where(PlanORM.plan_date <= date_to)

    total = db.execute(query.with_only_columns(func.count()).order_by(None)).scalar_one()

    rows = db.execute(
        query.order_by(PlanORM.plan_date.desc(), PlanORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    items = []
    for r in rows:
        tasks = _load_plan_tasks(db, r.id)
        items.append(Plan.model_validate(_orm_plan_to_dict(r, tasks)))

    return PlanList(
        items=items,
        pagination=Pagination(page=page, pageSize=page_size, total=total),
    )


@router.get("/{plan_id}", response_model=Plan, summary="计划详情")
def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Plan:
    row = db.get(PlanORM, plan_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "计划不存在"},
        )
    tasks = _load_plan_tasks(db, plan_id)
    return Plan.model_validate(_orm_plan_to_dict(row, tasks))


@router.patch(
    "/{plan_id}/tasks/{task_id}",
    response_model=PlanTaskDetail,
    summary="调整任务 / 确认完成情况",
)
def update_plan_task(
    plan_id: str,
    task_id: str,
    body: PlanTaskUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> PlanTaskDetail:
    # 先校验计划存在且属于当前用户
    plan_row = db.get(PlanORM, plan_id)
    if plan_row is None or plan_row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "计划不存在"},
        )

    task_row = db.get(PlanTaskORM, task_id)
    if task_row is None or task_row.plan_id != plan_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "任务不存在"},
        )

    if body.estimated_minutes is not None:
        task_row.estimated_minutes = body.estimated_minutes
    if body.status is not None:
        task_row.status = body.status.value
    if body.removed is not None:
        task_row.removed = body.removed

    # 任一字段被显式传入了 → 标记用户调整过（算法反馈信号）
    task_row.user_adjusted = True

    db.commit()
    db.refresh(task_row)

    return PlanTaskDetail.model_validate({
        "taskId": task_row.id,
        "subject": task_row.subject,
        "topic": task_row.topic,
        "estimatedMinutes": task_row.estimated_minutes,
        "priority": task_row.priority,
        "status": task_row.status,
        "goalId": task_row.goal_id,
        "removed": task_row.removed,
        "userAdjusted": task_row.user_adjusted,
        "updatedAt": task_row.updated_at.isoformat(),
    })

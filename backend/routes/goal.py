"""/goals 系列。

阶段 3（已接入）：create/list/patch 全部落库，不再返 mock 常量。
进度（plannedTasks/completedTasks/ratio）从 plan_tasks 表实时聚合：
  - plannedTasks  = 该 goal 关联的、未软删除的任务数
  - completedTasks = 其中 status=completed 的任务数
归档代替删除（openapi.yaml 2.3）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.goal import Goal as GoalORM
from models.plan import PlanTask as PlanTaskORM
from schemas.common import Pagination
from schemas.goal import Goal, GoalCreate, GoalList, GoalSummary, GoalUpdate
from schemas.user import User
from state_calculator import gen_id
from .deps import current_user

router = APIRouter(prefix="/goals", tags=["学习目标"])


def _aggregate_progress(db: Session, goal_id: str) -> dict:
    """从 plan_tasks 表实时聚合该目标的进度。

    plannedTasks  = 未软删除（removed=False）且 goal_id 匹配的任务数
    completedTasks = 其中 status='completed' 的任务数
    ratio = completedTasks / plannedTasks（plannedTasks=0 时为 0.0）
    """
    planned = db.execute(
        select(func.count())
        .select_from(PlanTaskORM)
        .where(
            PlanTaskORM.goal_id == goal_id,
            PlanTaskORM.removed.is_(False),
        )
    ).scalar_one()
    completed = db.execute(
        select(func.count())
        .select_from(PlanTaskORM)
        .where(
            PlanTaskORM.goal_id == goal_id,
            PlanTaskORM.removed.is_(False),
            PlanTaskORM.status == "completed",
        )
    ).scalar_one()
    ratio = (completed / planned) if planned > 0 else 0.0
    return {
        "plannedTasks": planned,
        "completedTasks": completed,
        "ratio": ratio,
    }


def _orm_to_goal_summary(row: GoalORM, progress: dict) -> dict:
    """ORM Goal → GoalSummary 形状（camelCase dict）。"""
    return {
        "goalId": row.id,
        "type": row.type,
        "subject": row.subject,
        "title": row.title,
        "targetDate": row.target_date.isoformat() if row.target_date else None,
        "status": row.status,
        "outcome": row.outcome,
        "completionNote": row.completion_note,
        "progress": progress,
    }


def _orm_to_goal(row: GoalORM, progress: dict) -> dict:
    """ORM Goal → Goal 完整形状（含 description / createdAt）。"""
    payload = _orm_to_goal_summary(row, progress)
    payload["description"] = row.description
    payload["createdAt"] = row.created_at.isoformat()
    return payload


@router.post("", response_model=Goal, status_code=status.HTTP_201_CREATED, summary="创建学习目标 ①")
def create_goal(
    body: GoalCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Goal:
    goal_id = gen_id("g")
    row = GoalORM(
        id=goal_id,
        user_id=_user.user_id,
        type=body.type.value,
        subject=body.subject.value,
        title=body.title,
        description=body.description,
        target_date=body.target_date,
        template_id=body.template_id,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # 新建目标无关联任务，进度全 0
    progress = {"plannedTasks": 0, "completedTasks": 0, "ratio": 0.0}
    return Goal.model_validate(_orm_to_goal(row, progress))


@router.get("", response_model=GoalList, summary="目标列表（含进度）")
def list_goals(
    status: str = "active",
    subject: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> GoalList:
    query = select(GoalORM).where(GoalORM.user_id == _user.user_id)
    # 契约枚举 [active, archived, all]；默认 active。all 不加过滤。
    if status and status != "all":
        query = query.where(GoalORM.status == status)
    if subject:
        query = query.where(GoalORM.subject == subject)

    total = db.execute(query.with_only_columns(func.count()).order_by(None)).scalar_one()

    rows = db.execute(
        query.order_by(GoalORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    items = [_orm_to_goal_summary(r, _aggregate_progress(db, r.id)) for r in rows]
    return GoalList(
        items=[GoalSummary.model_validate(it) for it in items],
        pagination=Pagination(page=page, pageSize=page_size, total=total),
    )


@router.get("/{goal_id}", response_model=Goal, summary="获取目标详情")
def get_goal(
    goal_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Goal:
    """单条目标详情（含 description，列表 GoalSummary 不含）。"""
    row = db.get(GoalORM, goal_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "目标不存在"},
        )
    progress = _aggregate_progress(db, row.id)
    return Goal.model_validate(_orm_to_goal(row, progress))


@router.patch("/{goal_id}", response_model=Goal, summary="更新 / 归档目标")
def update_goal(
    goal_id: str,
    body: GoalUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Goal:
    row = db.get(GoalORM, goal_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "目标不存在"},
        )

    if body.title is not None:
        row.title = body.title
    if body.description is not None:
        row.description = body.description
    if body.target_date is not None:
        row.target_date = body.target_date
    if body.status is not None:
        # 仅允许 active / archived（归档代替删除）
        if body.status not in ("active", "archived"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": "status 仅支持 active / archived",
                    "field": "status",
                },
            )
        row.status = body.status
    # 归档终态 + 完成总结（仅 archived 时有意义，但不在后端强制——前端控制时机）
    if body.outcome is not None:
        if body.outcome not in ("achieved", "abandoned", "expired"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": "outcome 仅支持 achieved / abandoned / expired",
                    "field": "outcome",
                },
            )
        row.outcome = body.outcome
    if body.completion_note is not None:
        row.completion_note = body.completion_note

    db.commit()
    db.refresh(row)

    progress = _aggregate_progress(db, row.id)
    return Goal.model_validate(_orm_to_goal(row, progress))

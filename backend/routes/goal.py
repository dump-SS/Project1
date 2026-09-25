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
from models.exam import Exam as ExamORM
from models.goal import Goal as GoalORM
from models.plan import PlanTask as PlanTaskORM
from schemas.common import Pagination
from schemas.goal import Goal, GoalCreate, GoalList, GoalSummary, GoalUpdate
from schemas.user import User
from state_calculator import gen_id
from .deps import current_user

router = APIRouter(prefix="/goals", tags=["学习目标"])


def _bad_request(message: str, field: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "VALIDATION_FAILED", "message": message, "field": field},
    )


def _validate_parent(db: Session, user_id: str, goal_id: str | None, parent_goal_id: str | None) -> None:
    """父子树（D6/D29）的引用校验。

    三件事必须挡住，否则树会坏掉且前端无从修复：
    1. 父目标不存在 / 不属于本人（跨用户引用 = 越权读别人的目标树）；
    2. 自己当自己的父；
    3. **成环**（A 的父是 B、B 的父又是 A）——环会让任何"沿父链上溯"的渲染或统计死循环。
    """
    if parent_goal_id is None:
        return
    if goal_id is not None and parent_goal_id == goal_id:
        raise _bad_request("不能把目标设为自己的父目标", "parentGoalId")

    parent = db.get(GoalORM, parent_goal_id)
    if parent is None or parent.user_id != user_id:
        raise _bad_request("父目标不存在", "parentGoalId")

    # 沿父链上溯查环（同时兜住历史脏数据造成的既有环）
    seen: set[str] = set()
    cursor: GoalORM | None = parent
    while cursor is not None and cursor.id not in seen:
        if goal_id is not None and cursor.id == goal_id:
            raise _bad_request("父子关系不能成环（该目标是其父目标的祖先）", "parentGoalId")
        seen.add(cursor.id)
        cursor = db.get(GoalORM, cursor.parent_goal_id) if cursor.parent_goal_id else None


def _validate_exam(db: Session, user_id: str, exam_id: str | None) -> None:
    """Goal 引用的考试必须存在且属于本人（D49）。"""
    if exam_id is None:
        return
    exam = db.get(ExamORM, exam_id)
    if exam is None or exam.user_id != user_id:
        raise _bad_request("关联的考试不存在", "examId")


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
    import json as _json

    point_ids = []
    if row.point_ids:
        try:
            point_ids = _json.loads(row.point_ids)
        except (ValueError, TypeError):
            point_ids = []
    return {
        "goalId": row.id,
        "type": row.type,
        "subject": row.subject,
        "title": row.title,
        "targetDate": row.target_date.isoformat() if row.target_date else None,
        "status": row.status,
        "outcome": row.outcome,
        "completionNote": row.completion_note,
        "pointIds": point_ids,
        "parentGoalId": row.parent_goal_id,
        "examId": row.exam_id,
        "targetScore": row.target_score,
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
    # 父子树与考试引用先校验（D6/D49）：引用不存在或跨用户的 id 一律 400，
    # 不留"建出来但指向空"的脏数据——树一旦有悬空父节点，前端渲染就无从兜底。
    _validate_parent(db, _user.user_id, None, body.parent_goal_id)
    _validate_exam(db, _user.user_id, body.exam_id)

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
        point_ids=__import__("json").dumps(body.point_ids) if body.point_ids else None,
        parent_goal_id=body.parent_goal_id,
        exam_id=body.exam_id,
        target_score=body.target_score,
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
    if body.point_ids is not None:
        row.point_ids = __import__("json").dumps(body.point_ids)

    # 父子树（D6/D29）：显式传 null = 提升为顶层目标，与「不传=不动」必须区分
    provided = body.model_fields_set
    if "parent_goal_id" in provided:
        _validate_parent(db, _user.user_id, row.id, body.parent_goal_id)
        row.parent_goal_id = body.parent_goal_id
    if "exam_id" in provided:
        _validate_exam(db, _user.user_id, body.exam_id)
        row.exam_id = body.exam_id
    if "target_score" in provided:
        row.target_score = body.target_score

    db.commit()
    db.refresh(row)

    progress = _aggregate_progress(db, row.id)
    return Goal.model_validate(_orm_to_goal(row, progress))

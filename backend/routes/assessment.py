"""/assessments 系列。阶段 3：从 DB 读记录，用 state_engine 计算窗口。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.assessment import AssessmentSnapshot as AssessmentSnapshotORM
from models.learning_record import LearningRecord as LearningRecordORM
from schemas.assessment import (
    AssessmentFeedback,
    AssessmentHistory,
    StateResultList,
)
from schemas.user import User
from state_calculator import (
    compute_window_for_records,
    gen_id,
    orm_record_to_engine_input,
    window_to_state_result_payload,
)
from .deps import current_user

router = APIRouter(prefix="/assessments", tags=["状态评估"])


def _window_rows(db: Session, user_id: str, subject: str, limit: int = 7) -> list[LearningRecordORM]:
    """最近 limit 条记录，时间正序。排序键含 created_at + id 以保证确定性
    （同一 started_at 下顺序不定会让趋势斜率符号反转，见 learning_record._window_rows 注释）。"""
    rows = db.execute(
        select(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.subject == subject,
        )
        .order_by(
            LearningRecordORM.started_at.desc(),
            LearningRecordORM.created_at.desc(),
            LearningRecordORM.id.desc(),
        )
        .limit(limit)
    ).scalars().all()
    return list(reversed(rows))


def _state_result_for_subject(
    db: Session, user_id: str, subject: str
) -> dict:
    """计算该学科的状态结果（camelCase dict for StateResult）。"""
    rows = _window_rows(db, user_id, subject)
    if not rows:
        return {
            "assessmentId": None,
            "subject": subject,
            "stateLabel": "insufficient_data",
            "displayText": "数据积累中，再记录几次就能给出判断",
            "dataSufficient": False,
            "recordCount": 0,
            "windowSize": 7,
        }
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]
    # 权重从用户级权重表读（同 learning_record.py）
    from .learning_record import _get_user_weights
    weights = _get_user_weights(db, user_id)
    window = compute_window_for_records(engine_inputs, weights=weights)

    # GET 是纯读，不该有写副作用——之前每次 GET 都 add+commit 一条快照，
    # 轮询/刷新会产生重复快照，污染 GET /assessments 的历史曲线（同一天出现多个同分点）。
    # 快照只应在提交/删除记录时落库（learning_record.py 的 _recompute_snapshot 负责）。
    # 这里直接返回计算结果，assessmentId 用最新已落库快照的 id（若存在），否则 None。
    latest_snapshot = db.execute(
        select(AssessmentSnapshotORM)
        .where(
            AssessmentSnapshotORM.user_id == user_id,
            AssessmentSnapshotORM.subject == subject,
            AssessmentSnapshotORM.data_sufficient == True,  # noqa: E712
        )
        .order_by(AssessmentSnapshotORM.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    snapshot_id = latest_snapshot.id if latest_snapshot and window.data_sufficient else None

    return window_to_state_result_payload(
        window, subject, snapshot_id, [r.id for r in rows]
    )


@router.get("/current", response_model=StateResultList, summary="获取当前状态与标签 ④")
def get_current_assessments(
    subject: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> StateResultList:
    if subject:
        subjects = [subject]
    else:
        # 查询该用户有记录的学科
        result = db.execute(
            select(LearningRecordORM.subject)
            .where(LearningRecordORM.user_id == _user.user_id)
            .distinct()
        ).scalars().all()
        subjects = sorted(set(result)) if result else []

    items = [_state_result_for_subject(db, _user.user_id, s) for s in subjects]
    return StateResultList.model_validate({"items": items})


@router.get("", response_model=AssessmentHistory, summary="状态历史（趋势曲线）")
def list_assessment_history(
    subject: str,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> AssessmentHistory:
    query = select(AssessmentSnapshotORM).where(
        AssessmentSnapshotORM.user_id == _user.user_id,
        AssessmentSnapshotORM.subject == subject,
    )
    if date_from:
        query = query.where(AssessmentSnapshotORM.computed_at >= date_from)
    if date_to:
        query = query.where(AssessmentSnapshotORM.computed_at <= date_to)
    query = query.order_by(AssessmentSnapshotORM.computed_at.asc())
    rows = db.execute(query).scalars().all()

    items = []
    for row in rows:
        items.append({
            "date": str(row.computed_at.date()),
            "windowScore": row.window_score,
            "stateLabel": row.state_label,
            "trend": row.trend,
        })

    return AssessmentHistory.model_validate({"subject": subject, "items": items})


@router.put(
    "/{assessment_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="提交「这个判断准不准」反馈",
)
def put_assessment_feedback(
    assessment_id: str,
    body: AssessmentFeedback,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    """记录反馈（当前仅受理，不做后续处理——AI 调权链路待接入）。"""
    # TODO: 持久化反馈到 feedback 表，供 AI 调权迭代使用
    _ = (assessment_id, body.accurate, _user.user_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
"""/summaries 系列。阶段 3：落库 + ai_suggestion 引擎。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_suggestion import generate_summary
from database import get_db
from models.summary import Summary as SummaryORM
from schemas.common import RatingFeedback
from schemas.summary import (
    Summary,
    SummaryCreate,
    SummaryFeedbackResult,
    SummaryList,
    SummaryPending,
)
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/summaries", tags=["学习总结与复盘"])


def _gen_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _orm_to_dict(row: SummaryORM) -> dict:
    """ORM 行 → 契约 camelCase dict。"""
    base: dict = {
        "summaryId": row.id,
        "periodStart": row.period_start.isoformat() if row.period_start else None,
        "periodEnd": row.period_end.isoformat() if row.period_end else None,
        "generation": {"status": row.generation_status},
        "feedback": None,
    }
    if row.generation_source:
        base["generation"]["source"] = row.generation_source
    if row.generation_completed_at:
        base["generation"]["completedAt"] = row.generation_completed_at.isoformat()

    if row.content_overview:
        base["content"] = {
            "overview": row.content_overview,
            "patterns": json.loads(row.content_patterns) if row.content_patterns else [],
            "suggestions": json.loads(row.content_suggestions) if row.content_suggestions else [],
            "encouragement": row.content_encouragement,
        }
    else:
        base["content"] = None

    data_points: dict = {}
    if row.data_record_count is not None:
        data_points["recordCount"] = row.data_record_count
    if row.data_subjects:
        data_points["subjects"] = json.loads(row.data_subjects)
    if row.data_plan_completion_ratio is not None:
        data_points["planCompletionRatio"] = row.data_plan_completion_ratio
    if row.data_referenced_assessment_ids:
        data_points["referencedAssessmentIds"] = json.loads(row.data_referenced_assessment_ids)
    if row.data_min_required is not None:
        data_points["minRequired"] = row.data_min_required
    if data_points:
        base["dataPoints"] = data_points

    if row.message:
        base["message"] = row.message

    if row.feedback_rating:
        base["feedback"] = {
            "rating": row.feedback_rating,
            "reason": row.feedback_reason,
            "submittedAt": row.feedback_submitted_at.isoformat() if row.feedback_submitted_at else None,
        }

    return base


@router.post(
    "",
    response_model=SummaryPending,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动触发生成复盘",
)
def create_summary(
    body: SummaryCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> SummaryPending:
    summ_id = _gen_id("sum")

    summ = SummaryORM(
        id=summ_id,
        user_id=_user.user_id,
        period_start=body.period_start,
        period_end=body.period_end,
        generation_status="pending",
    )
    db.add(summ)
    db.commit()

    # 同步生成
    generate_summary(db, summ_id, _user.user_id, body.period_start, body.period_end)

    return SummaryPending.model_validate({
        "summaryId": summ_id,
        "periodStart": body.period_start.isoformat(),
        "periodEnd": body.period_end.isoformat(),
        "generation": {"status": "pending"},
        "createdAt": summ.created_at.isoformat(),
    })


@router.get("", response_model=SummaryList, summary="复盘列表")
def list_summaries(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> SummaryList:
    rows = db.execute(
        select(SummaryORM)
        .where(SummaryORM.user_id == _user.user_id)
        .order_by(SummaryORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    total = len(db.execute(
        select(SummaryORM).where(SummaryORM.user_id == _user.user_id)
    ).scalars().all())

    items = [_orm_to_dict(r) for r in rows]
    return SummaryList(
        items=items,
        pagination={"page": page, "pageSize": page_size, "total": total},
    )


@router.get("/{summary_id}", response_model=Summary, summary="获取复盘详情")
def get_summary(
    summary_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Summary:
    row = db.get(SummaryORM, summary_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘不存在"},
        )
    return Summary.model_validate(_orm_to_dict(row))


@router.put(
    "/{summary_id}/feedback",
    response_model=SummaryFeedbackResult,
    summary="提交复盘反馈",
)
def put_summary_feedback(
    summary_id: str,
    body: RatingFeedback,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> SummaryFeedbackResult:
    row = db.get(SummaryORM, summary_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘不存在"},
        )
    row.feedback_rating = body.rating.value
    row.feedback_reason = body.reason
    row.feedback_submitted_at = datetime.utcnow()
    db.commit()

    return SummaryFeedbackResult.model_validate({
        "summaryId": summary_id,
        "feedback": {
            "rating": body.rating.value,
            "reason": body.reason,
            "submittedAt": row.feedback_submitted_at.isoformat(),
        },
    })
"""/recommendations 系列。阶段 3：落库 + ai_suggestion 引擎。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_suggestion import run_recommendation_generation
from database import get_db
from models.recommendation import Recommendation as RecommendationORM
from models.learning_record import LearningRecord
from schemas.common import RatingFeedback
from schemas.recommendation import (
    Recommendation,
    RecommendationCreate,
    RecommendationFeedbackResult,
    RecommendationList,
    RecommendationPending,
)
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/recommendations", tags=["个性化建议"])


def _gen_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _orm_to_dict(row: RecommendationORM) -> dict:
    """ORM 行 → 契约 camelCase dict。"""
    items = json.loads(row.items) if row.items else None
    base = {
        "recommendationId": row.id,
        "scene": row.scene,
        "subject": row.subject,
        "generation": {
            "status": row.generation_status,
        },
        "items": items,
        "feedback": None,
    }
    if row.generation_source:
        base["generation"]["source"] = row.generation_source
    if row.generation_completed_at:
        base["generation"]["completedAt"] = row.generation_completed_at.isoformat()
    if row.based_on_state_label or row.based_on_explain:
        base["basedOn"] = {
            "assessmentId": row.based_on_assessment_id,
            "recordId": row.based_on_record_id,
            "stateLabel": row.based_on_state_label,
            "explain": row.based_on_explain,
        }
    if row.feedback_rating:
        base["feedback"] = {
            "rating": row.feedback_rating,
            "reason": row.feedback_reason,
            "submittedAt": row.feedback_submitted_at.isoformat() if row.feedback_submitted_at else None,
        }
    return base


@router.post(
    "",
    response_model=RecommendationPending,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动请求生成建议",
)
def create_recommendation(
    body: RecommendationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> RecommendationPending:
    """插入 pending 行，生成挂后台（PRD 6.4），立即返回 202 + id。"""
    rec_id = _gen_id("rec")

    # 找关联的 record（post_session 场景）
    trigger_record = None
    if body.record_id:
        trigger_record = db.get(LearningRecord, body.record_id)

    rec = RecommendationORM(
        id=rec_id,
        user_id=_user.user_id,
        scene=body.scene.value,
        subject=body.subject.value if body.subject else (trigger_record.subject if trigger_record else None),
        generation_status="pending",
        record_id=body.record_id,
    )
    db.add(rec)
    db.commit()

    # PRD 6.4：LLM 调用挂后台，POST 立即返回（详见 learning_record.py 同款注释）
    background_tasks.add_task(
        run_recommendation_generation,
        rec_id, _user.user_id, body.scene.value, rec.subject, body.record_id,
    )

    return RecommendationPending.model_validate({
        "recommendationId": rec_id,
        "scene": body.scene.value,
        "subject": rec.subject,
        "generation": {"status": "pending"},
        "createdAt": rec.created_at.isoformat(),
    })


@router.get("", response_model=RecommendationList, summary="建议列表")
def list_recommendations(
    scene: str | None = None,
    subject: str | None = None,
    status: str = "ready",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> RecommendationList:
    query = select(RecommendationORM).where(RecommendationORM.user_id == _user.user_id)
    if status != "all":
        query = query.where(RecommendationORM.generation_status == status)
    if scene:
        query = query.where(RecommendationORM.scene == scene)
    if subject:
        query = query.where(RecommendationORM.subject == subject)
    query = query.order_by(RecommendationORM.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(query).scalars().all()

    total_query = select(RecommendationORM).where(RecommendationORM.user_id == _user.user_id)
    if status != "all":
        total_query = total_query.where(RecommendationORM.generation_status == status)
    total = len(db.execute(total_query).scalars().all())

    items = [_orm_to_dict(r) for r in rows]
    return RecommendationList(
        items=items,
        pagination={"page": page, "pageSize": page_size, "total": total},
    )


@router.get("/{recommendation_id}", response_model=Recommendation, summary="获取建议内容 ⑤")
def get_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Recommendation:
    row = db.get(RecommendationORM, recommendation_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "建议不存在"},
        )
    return Recommendation.model_validate(_orm_to_dict(row))


@router.put(
    "/{recommendation_id}/feedback",
    response_model=RecommendationFeedbackResult,
    summary="提交建议反馈",
)
def put_recommendation_feedback(
    recommendation_id: str,
    body: RatingFeedback,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> RecommendationFeedbackResult:
    row = db.get(RecommendationORM, recommendation_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "建议不存在"},
        )
    row.feedback_rating = body.rating.value
    row.feedback_reason = body.reason
    row.feedback_submitted_at = datetime.utcnow()
    db.commit()

    return RecommendationFeedbackResult.model_validate({
        "recommendationId": recommendation_id,
        "feedback": {
            "rating": body.rating.value,
            "reason": body.reason,
            "submittedAt": row.feedback_submitted_at.isoformat(),
        },
    })
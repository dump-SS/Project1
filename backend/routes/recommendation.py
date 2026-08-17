"""/recommendations 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import RECOMMENDATION_LIST_MOCK
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


@router.post(
    "",
    response_model=RecommendationPending,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动请求生成建议",
)
def create_recommendation(
    body: RecommendationCreate, _user: User = Depends(current_user)
) -> RecommendationPending:
    return RecommendationPending.model_validate(
        {
            "recommendationId": "rec_20301",
            "scene": body.scene,
            "subject": body.subject,
            "generation": {"status": "pending"},
            "createdAt": "2026-08-16T19:46:02+08:00",
        }
    )


@router.get("", response_model=RecommendationList, summary="建议列表")
def list_recommendations(
    scene: str | None = None,
    subject: str | None = None,
    status: str = "ready",
    page: int = 1,
    page_size: int = 20,
    _user: User = Depends(current_user),
) -> RecommendationList:
    return RECOMMENDATION_LIST_MOCK


@router.get("/{recommendation_id}", response_model=Recommendation, summary="获取建议内容 ⑤")
def get_recommendation(
    recommendation_id: str, _user: User = Depends(current_user)
) -> Recommendation:
    return RECOMMENDATION_LIST_MOCK.items[0]


@router.put(
    "/{recommendation_id}/feedback",
    response_model=RecommendationFeedbackResult,
    summary="提交建议反馈",
)
def put_recommendation_feedback(
    recommendation_id: str,
    body: dict,
    _user: User = Depends(current_user),
) -> RecommendationFeedbackResult:
    return RecommendationFeedbackResult.model_validate(
        {
            "recommendationId": recommendation_id,
            "feedback": {
                "rating": body.get("rating", "useful"),
                "reason": body.get("reason"),
                "submittedAt": "2026-08-16T19:50:00+08:00",
            },
        }
    )

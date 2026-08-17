"""/assessments 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import ASSESSMENT_HISTORY_MOCK, STATE_RESULT_LIST_MOCK
from schemas.assessment import (
    AssessmentFeedback,
    AssessmentHistory,
    StateResultList,
)
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/assessments", tags=["状态评估"])


@router.get("/current", response_model=StateResultList, summary="获取当前状态与标签 ④")
def get_current_assessments(
    subject: str | None = None, _user: User = Depends(current_user)
) -> StateResultList:
    return STATE_RESULT_LIST_MOCK


@router.get("", response_model=AssessmentHistory, summary="状态历史（趋势曲线）")
def list_assessment_history(
    subject: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _user: User = Depends(current_user),
) -> AssessmentHistory:
    return ASSESSMENT_HISTORY_MOCK


@router.put(
    "/{assessment_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="提交「这个判断准不准」反馈",
)
def put_assessment_feedback(
    assessment_id: str,
    body: AssessmentFeedback,
    _user: User = Depends(current_user),
) -> None:
    # mock：什么都不做
    return None

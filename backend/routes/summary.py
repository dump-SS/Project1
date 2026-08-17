"""/summaries 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import SUMMARY_LIST_MOCK
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


@router.post(
    "",
    response_model=SummaryPending,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动触发生成复盘",
)
def create_summary(
    body: SummaryCreate, _user: User = Depends(current_user)
) -> SummaryPending:
    return SummaryPending.model_validate(
        {
            "summaryId": "sum_4402",
            "periodStart": body.period_start.isoformat(),
            "periodEnd": body.period_end.isoformat(),
            "generation": {"status": "pending"},
            "createdAt": "2026-08-16T22:00:00+08:00",
        }
    )


@router.get("", response_model=SummaryList, summary="复盘列表")
def list_summaries(
    page: int = 1, page_size: int = 20, _user: User = Depends(current_user)
) -> SummaryList:
    return SUMMARY_LIST_MOCK


@router.get("/{summary_id}", response_model=Summary, summary="获取复盘详情")
def get_summary(summary_id: str, _user: User = Depends(current_user)) -> Summary:
    return SUMMARY_LIST_MOCK.items[0]


@router.put(
    "/{summary_id}/feedback",
    response_model=SummaryFeedbackResult,
    summary="提交复盘反馈",
)
def put_summary_feedback(
    summary_id: str,
    body: dict,
    _user: User = Depends(current_user),
) -> SummaryFeedbackResult:
    return SummaryFeedbackResult.model_validate(
        {
            "summaryId": summary_id,
            "feedback": {
                "rating": body.get("rating", "useful"),
                "reason": body.get("reason"),
                "submittedAt": "2026-08-16T22:10:00+08:00",
            },
        }
    )

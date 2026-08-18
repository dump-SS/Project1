"""/daily-summary 系列。PRD 5.3：单日一句话总结。

与 /summaries（3-31 天复盘）解耦：日总结是派生态，per-day 调用，不入库。
"""
from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from daily_summary import generate_day_summary
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/daily-summary", tags=["日总结"])


class DailySummaryResponse(BaseModel):
    """日总结响应（openapi 0.2 错误格式不在此处，单一成功字段）。"""

    model_config = ConfigDict(populate_by_name=True)

    date: str = Field(..., description="YYYY-MM-DD")
    summary: str = Field(..., description="一句话总结（≤60 字）")


@router.get(
    "",
    response_model=DailySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="单日一句话学习总结",
)
def get_daily_summary(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> DailySummaryResponse:
    # 校验日期格式（避免脏查询落到 SQL）
    try:
        _date.fromisoformat(date)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_FAILED", "message": "日期格式应为 YYYY-MM-DD", "field": "date"},
        )

    summary = generate_day_summary(db, _user.user_id, date)
    return DailySummaryResponse.model_validate({"date": date, "summary": summary})

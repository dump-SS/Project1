"""
状态评估（openapi.yaml 5.x）

StateBasedOn / StateResult / StateResultList / AssessmentHistoryPoint / AssessmentHistory / AssessmentFeedback
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import StateLabel, Subject, Trend


class StateBasedOn(BaseModel):
    """可解释性依据（PRD 8.3），不暴露权重与公式。"""

    record_ids: list[str] = Field(..., alias="recordIds")
    signals: list[str] = Field(..., description="面向用户的信号说明")


class StateResult(BaseModel):
    """单学科当前状态结果；数据不足时 assessmentId 为 null 且不输出 windowScore / trend。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "assessmentId": "a_7742",
                "subject": "math",
                "windowScore": 0.48,
                "trend": "down",
                "stateLabel": "fatigue_warning",
                "displayText": "最近几次数学状态有点走低，疲劳感比较明显",
                "dataSufficient": True,
                "recordCount": 7,
                "windowSize": 7,
                "basedOn": {
                    "recordIds": ["r_88012", "r_87990", "r_87944"],
                    "signals": ["自评疲劳度连续 3 次 ≥4", "练习正确率较上周下降"],
                },
                "computedAt": "2026-08-16T19:46:00+08:00",
            }
        },
    )

    assessment_id: str | None = Field(None, alias="assessmentId", description="数据不足时为 null")
    subject: Subject
    window_score: float | None = Field(None, alias="windowScore", description="数据不足时不返回")
    trend: Trend | None = Field(None, description="数据不足时不返回")
    state_label: StateLabel = Field(..., alias="stateLabel")
    display_text: str = Field(..., alias="displayText", description="面向用户的自然语言说明")
    data_sufficient: bool = Field(..., alias="dataSufficient")
    record_count: int = Field(..., alias="recordCount")
    window_size: int = Field(..., alias="windowSize")
    based_on: StateBasedOn | None = Field(None, alias="basedOn")
    computed_at: datetime | None = Field(None, alias="computedAt")


class StateResultList(BaseModel):
    """当前状态响应；不传 subject 时返回全部学科（不做跨学科加权综合）。"""

    items: list[StateResult]


class AssessmentHistoryPoint(BaseModel):
    """趋势曲线上的单个数据点。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "date": "2026-08-16",
                "windowScore": 0.48,
                "stateLabel": "fatigue_warning",
                "trend": "down",
            }
        },
    )

    date: date
    window_score: float = Field(..., alias="windowScore")
    state_label: StateLabel = Field(..., alias="stateLabel")
    trend: Trend


class AssessmentHistory(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "subject": "math",
                "items": [
                    {"date": "2026-08-14", "windowScore": 0.61, "stateLabel": "efficient_stable", "trend": "flat"},
                    {"date": "2026-08-15", "windowScore": 0.55, "stateLabel": "fluctuating_up", "trend": "down"},
                    {"date": "2026-08-16", "windowScore": 0.48, "stateLabel": "fatigue_warning", "trend": "down"},
                ],
            }
        },
    )

    subject: Subject
    items: list[AssessmentHistoryPoint]


class AssessmentFeedback(BaseModel):
    """「这个判断准不准」反馈请求体。"""

    accurate: bool = Field(..., description="判断是否准确")

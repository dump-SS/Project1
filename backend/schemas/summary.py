"""
学习总结与复盘（openapi.yaml 7.x）

SummaryContent / SummaryDataPoints / Summary / SummaryPending / SummaryCreate
SummaryList / SummaryFeedbackResult
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import FeedbackRecord, GenerationStatus, Pagination
from .enums import Subject


class SummaryContent(BaseModel):
    """复盘固定输出框架（PRD 5.4），数据不足时整体为 null。"""

    overview: str
    patterns: list[str]
    suggestions: list[str]
    encouragement: str


class SummaryDataPoints(BaseModel):
    """复盘引用的数据点；数据不足时返回 recordCount 与 minRequired。"""

    model_config = ConfigDict(populate_by_name=True)

    record_count: int | None = Field(None, alias="recordCount")
    subjects: list[Subject] | None = None
    plan_completion_ratio: float | None = Field(None, alias="planCompletionRatio")
    # 今日计划完成计数（PRD 5.4：让前端 SummaryCard 显示「今日已完成 N / M」）
    plan_completed_count: int | None = Field(None, alias="planCompletedCount")
    plan_total_count: int | None = Field(None, alias="planTotalCount")
    referenced_assessment_ids: list[str] | None = Field(None, alias="referencedAssessmentIds")
    min_required: int | None = Field(None, alias="minRequired")


class Summary(BaseModel):
    """复盘详情。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "summaryId": "sum_4402",
                "periodStart": "2026-08-10",
                "periodEnd": "2026-08-16",
                "generation": {
                    "status": "ready",
                    "source": "llm",
                    "completedAt": "2026-08-16T22:00:12+08:00",
                },
                "content": {
                    "overview": "这周数学从「高效稳定」滑到了「疲劳预警」",
                    "patterns": ["数学安排在 21 点后的 3 次记录，完成度都是部分完成"],
                    "suggestions": ["把数学挪到下午或晚饭后早一点的时段试一周"],
                    "encouragement": "状态有起伏很正常",
                },
                "dataPoints": {
                    "recordCount": 9,
                    "subjects": ["math", "english"],
                    "planCompletionRatio": 0.61,
                    "referencedAssessmentIds": ["a_7742", "a_7710"],
                },
                "feedback": None,
            }
        },
    )

    summary_id: str = Field(..., alias="summaryId")
    period_start: date | None = Field(None, alias="periodStart")
    period_end: date | None = Field(None, alias="periodEnd")
    generation: GenerationStatus
    content: SummaryContent | None = None
    data_points: SummaryDataPoints | None = Field(None, alias="dataPoints")
    message: str | None = None
    feedback: FeedbackRecord | None = None


class SummaryPending(BaseModel):
    """手动触发复盘后的受理响应。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "summaryId": "sum_4402",
                "periodStart": "2026-08-10",
                "periodEnd": "2026-08-16",
                "generation": {"status": "pending"},
                "createdAt": "2026-08-16T22:00:00+08:00",
            }
        },
    )

    summary_id: str = Field(..., alias="summaryId")
    period_start: date = Field(..., alias="periodStart")
    period_end: date = Field(..., alias="periodEnd")
    generation: GenerationStatus
    created_at: datetime = Field(..., alias="createdAt")


class SummaryCreate(BaseModel):
    """手动触发复盘请求体。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"periodStart": "2026-08-10", "periodEnd": "2026-08-16"}},
    )

    period_start: date = Field(..., alias="periodStart")
    period_end: date = Field(..., alias="periodEnd", description="区间长度 3-31 天")


class SummaryList(BaseModel):
    items: list[Summary]
    pagination: Pagination


class SummaryFeedbackResult(BaseModel):
    """复盘反馈提交结果。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "summaryId": "sum_4402",
                "feedback": {"rating": "useful", "reason": "观察到的时段规律挺准", "submittedAt": "2026-08-16T22:10:00+08:00"},
            }
        },
    )

    summary_id: str = Field(..., alias="summaryId")
    feedback: FeedbackRecord

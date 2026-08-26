"""
个性化建议（openapi.yaml 6.x）

RecommendationItem / RecommendationBasedOn / Recommendation / RecommendationPending
RecommendationCreate / RecommendationList / RecommendationFeedbackResult
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import FeedbackRecord, GenerationStatus, Pagination
from .enums import RecScene, Subject, StateLabel


class RecommendationItem(BaseModel):
    title: str
    content: str = Field(..., description="建议正文，口语化且贴合本次学习情况")


class RecommendationBasedOn(BaseModel):
    """建议的生成依据（PRD 6.5 留痕）。"""

    model_config = ConfigDict(populate_by_name=True)

    assessment_id: str | None = Field(None, alias="assessmentId")
    record_id: str | None = Field(None, alias="recordId")
    state_label: StateLabel | None = Field(None, alias="stateLabel")
    explain: str


class Recommendation(BaseModel):
    """建议详情；生成中时 items 为 null，兜底时 generation.source 为 template。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "recommendationId": "rec_20301",
                "scene": "post_session",
                "subject": "SX",
                "generation": {
                    "status": "ready",
                    "source": "llm",
                    "completedAt": "2026-08-16T19:46:09+08:00",
                },
                "items": [
                    {
                        "title": "把单次时长压到 25 分钟",
                        "content": "这次函数练了 45 分钟但中断了 3 次，后半程正确率明显掉下来了。",
                    }
                ],
                "basedOn": {
                    "assessmentId": "a_7742",
                    "recordId": "r_88012",
                    "stateLabel": "fatigue_warning",
                    "explain": "依据最近 7 次数学记录的疲劳自评与正确率变化",
                },
                "feedback": None,
            }
        },
    )

    recommendation_id: str = Field(..., alias="recommendationId")
    scene: RecScene
    subject: Subject | None = None
    generation: GenerationStatus
    items: list[RecommendationItem] | None = Field(None, description="生成中为 null")
    based_on: RecommendationBasedOn | None = Field(None, alias="basedOn")
    feedback: FeedbackRecord | None = None


class RecommendationPending(BaseModel):
    """手动请求建议后的受理响应。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "recommendationId": "rec_20301",
                "scene": "post_session",
                "subject": "SX",
                "generation": {"status": "pending"},
                "createdAt": "2026-08-16T19:46:02+08:00",
            }
        },
    )

    recommendation_id: str = Field(..., alias="recommendationId")
    scene: RecScene
    subject: Subject | None = None
    generation: GenerationStatus
    created_at: datetime = Field(..., alias="createdAt")


class RecommendationCreate(BaseModel):
    """手动请求生成建议请求体。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"scene": "post_session", "subject": "SX", "recordId": "r_88012"}},
    )

    scene: RecScene
    subject: Subject | None = Field(None, description="post_session 场景建议必填")
    record_id: str | None = Field(None, alias="recordId", description="post_session 场景关联的学习记录")


class RecommendationList(BaseModel):
    items: list[Recommendation]
    pagination: Pagination


class RecommendationFeedbackResult(BaseModel):
    """建议反馈提交结果。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "recommendationId": "rec_20301",
                "feedback": {"rating": "useful", "reason": None, "submittedAt": "2026-08-16T19:50:00+08:00"},
            }
        },
    )

    recommendation_id: str = Field(..., alias="recommendationId")
    feedback: FeedbackRecord

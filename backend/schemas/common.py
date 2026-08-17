"""
通用结构（openapi.yaml components.schemas 顶部）

Error / Pagination / GenerationStatus / RatingFeedback / FeedbackRecord
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import GenerationSource, Rating


class ErrorDetail(BaseModel):
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="可展示的错误说明")
    field: str | None = Field(None, description="校验失败的字段路径，仅参数校验错误时出现")


class Error(BaseModel):
    """统一错误格式（openapi.yaml 0.2 节）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "自评专注度必须为 1-5 的整数",
                    "field": "selfReport.focus",
                }
            }
        }
    )

    error: ErrorDetail


class Pagination(BaseModel):
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., alias="pageSize", description="每页条数")
    total: int = Field(..., description="总条数")


class GenerationStatus(BaseModel):
    """AI 异步生成状态。终态：ready / insufficient_data / failed。"""

    status: Literal["pending", "ready", "insufficient_data", "failed"] = Field(
        ..., description="生成状态"
    )
    source: GenerationSource | None = Field(None, description="llm / template")
    completed_at: datetime | None = Field(None, description="生成完成时间，终态时出现")


class RatingFeedback(BaseModel):
    """建议 / 复盘的有用性反馈请求体。"""

    rating: Rating = Field(..., description="useful / neutral / not_useful")
    reason: str | None = Field(None, max_length=100, description="可选，≤100 字，补充为什么不准")


class FeedbackRecord(BaseModel):
    """已提交的反馈。"""

    model_config = ConfigDict(populate_by_name=True)

    rating: Rating
    reason: str | None = Field(None, description="用户补充说明")
    submitted_at: datetime = Field(..., alias="submittedAt", description="提交时间")

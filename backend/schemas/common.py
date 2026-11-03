"""
通用结构（openapi.yaml components.schemas 顶部）

Error / Pagination / GenerationStatus / RatingFeedback / FeedbackRecord
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from .enums import GenerationSource, Rating



class APIModel(BaseModel):
    """全站响应基座（契约 v1.19.0）：datetime 字段统一发 **UTC 带时区后缀**（如 2026-11-03T12:00:00Z）。

    背景（P0 全站缺陷）：后端原先发**无时区后缀的裸 UTC**，前端按本地时区解析
    → 用户看到的时间全部差 8 小时。修法 = 序列化边界统一补时区：
    - 通配校验器把 naive datetime 补成 UTC-aware（历史数据/utcnow() 存的都是 naive UTC）；
    - `ser_json_tz='utc'` 把 aware 值归一到 UTC 输出 Z 后缀。
    """

    model_config = ConfigDict(ser_json_tz='utc')

    @field_validator('*', mode='after')
    @classmethod
    def _datetime_as_utc(cls, v: Any, info: ValidationInfo) -> Any:
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)  # naive 视为 UTC（utcnow() 存量口径）
            return v.astimezone(timezone.utc)  # aware 归一到 UTC（换表示不变绝对时刻）
        return v


class ErrorDetail(APIModel):
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="可展示的错误说明")
    field: str | None = Field(None, description="校验失败的字段路径，仅参数校验错误时出现")


class Error(APIModel):
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


class Pagination(APIModel):
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., alias="pageSize", description="每页条数")
    total: int = Field(..., description="总条数")


class GenerationStatus(APIModel):
    """AI 异步生成状态。终态：ready / insufficient_data / failed。"""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["pending", "ready", "insufficient_data", "failed"] = Field(
        ..., description="生成状态"
    )
    source: GenerationSource | None = Field(None, description="llm / template")
    completed_at: datetime | None = Field(None, alias="completedAt", description="生成完成时间，终态时出现")


class RatingFeedback(APIModel):
    """建议 / 复盘的有用性反馈请求体。"""

    rating: Rating = Field(..., description="useful / neutral / not_useful")
    reason: str | None = Field(None, max_length=100, description="可选，≤100 字，补充为什么不准")


class FeedbackRecord(APIModel):
    """已提交的反馈。"""

    model_config = ConfigDict(populate_by_name=True)

    rating: Rating
    reason: str | None = Field(None, description="用户补充说明")
    submitted_at: datetime = Field(..., alias="submittedAt", description="提交时间")

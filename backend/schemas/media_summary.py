"""#47 · 照片要点摘要响应模型（契约 v1.18.0）。

摘要**不落库**：本模型只在 POST /f/media/{key}/summary 的响应里出现一次。
summary 字段在服务层（media_summary.summarize_media）返回前已过
privacy_filter.sanitize_text —— 调用方可直接把它作为 snapshot.content 存入收藏。
"""
from pydantic import BaseModel, ConfigDict, Field

from schemas.enums import Subject


class MediaSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: str = Field(..., min_length=1, max_length=2000, description="要点摘要（markdown 列表），已脱敏")
    subject: Subject = Field(..., description="学科归类；无法归类时为 other")

"""D55 · 作业单照片抽取请求/响应模型（契约 v1.15.0）。

抽取结果「会话内不落库」：本模型只在 POST /f/worksheet/extract 的响应里出现一次，
用户在确认卡（D17 形态，前端渲染）里确认/修改后的最终任务列表另经
`POST /plans` 的 tasks 字段（schemas/plan.PlanTaskInput）落库为计划任务。
"""
from pydantic import BaseModel, ConfigDict, Field

from schemas.enums import Subject


class WorksheetExtractRequest(BaseModel):
    """抽取请求体：只需已上传照片的 key。"""

    model_config = ConfigDict(populate_by_name=True)

    media_key: str = Field(..., alias="mediaKey", min_length=1, description="已上传的作业单照片 key")


class WorksheetItem(BaseModel):
    """单个作业项。LLM 的越界输出由服务层截断后再构造本模型（见 worksheet_extract）。"""

    model_config = ConfigDict(populate_by_name=True)

    subject: Subject = Field(..., description="学科代码；无法归类时为 other")
    topic: str = Field(..., min_length=1, max_length=100, description="作业内容")
    estimated_minutes: int = Field(
        ...,
        alias="estimatedMinutes",
        ge=5,
        le=240,
        description="预估时长（分钟），服务端已截断到该范围",
    )


class WorksheetExtraction(BaseModel):
    """抽取结果（不落库，只在本响应返回一次）。"""

    items: list[WorksheetItem] = Field(..., min_length=1, max_length=20)

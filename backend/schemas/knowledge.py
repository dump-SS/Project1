"""知识复盘 + 错题归因 schema（PRD v1.4 板块二，P0 合规整改后）。

与旧版差异（对齐 docs/openapi.yaml v1.5）：
- ErrorParseRequest：不再接收 question_text/student_answer/correct_answer 原文，
  改为引用已入库错题（errorId）；原文只本地检索、永不出域。
- KnowledgeSummaryCreate：知识复盘请求改为结构化入参（学科/周期），
  不再接收前端自由拼装的 error_summary/mastery_changes/state_context 文本。
  v2.2 起改为 periodStart/periodEnd/subject 并异步落库 summaries 表。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSummaryCreate(BaseModel):
    """知识复盘请求（POST /api/v1/knowledge-summary）。"""

    model_config = ConfigDict(populate_by_name=True)

    subject: str = Field(..., alias="subject", description="学科，如 math / 数学")
    period: str = Field(..., alias="period", description="复盘周期，如「本周」")


class KnowledgeSummaryResponse(BaseModel):
    """知识复盘响应。"""

    summary: str = Field(..., description="LLM 生成的知识复盘文案")


class ErrorParseRequest(BaseModel):
    """错题归因请求（合规形态）。"""

    model_config = ConfigDict(populate_by_name=True)

    error_id: str = Field(..., alias="errorId", description="已入库错题 ID（err_ 前缀），原文不出域")


class ErrorParseResponse(BaseModel):
    """错题归因响应。"""

    parse: str = Field(..., description="LLM 生成的智能解析")

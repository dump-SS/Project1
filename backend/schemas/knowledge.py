"""知识复盘 + 错题解析（PRD v1.4 板块二）。

与板块一 5.4 复盘（summaries，`dimension=state_and_plan`）的边界：
本模块针对「学科知识内容维度」——输入是错题摘要 / 知识点掌握度变化 /
错题原文与作答，输出是知识复盘或错题解析文案。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeSummaryRequest(BaseModel):
    """知识复盘请求（POST /api/v1/knowledge-summary）。"""

    subject: str = Field(..., description="学科，如「数学」")
    period: str = Field(..., description="复盘周期，如「本周」")
    error_summary: str = Field(..., description="错题摘要，含数量与集中出错的知识点")
    mastery_changes: str = Field(..., description="知识点掌握度变化")
    state_context: str = Field(..., description="整体学习状态描述")


class KnowledgeSummaryResponse(BaseModel):
    """知识复盘响应。"""

    summary: str = Field(..., description="LLM 生成的知识复盘文案")


class MatchedKnowledge(BaseModel):
    """错题匹配到的知识点。"""

    name: str = Field(..., description="知识点名称")
    definition: str = Field(..., description="知识点定义")
    error_tip: str = Field(..., description="易错点提示")


class ErrorParseRequest(BaseModel):
    """错题解析请求（POST /api/v1/error-parse）。"""

    question_text: str = Field(..., description="题目内容")
    student_answer: str = Field(..., description="学生作答")
    correct_answer: str = Field(..., description="正确答案")
    matched_knowledge: MatchedKnowledge = Field(..., description="匹配到的知识点")


class ErrorParseResponse(BaseModel):
    """错题解析响应。"""

    parse: str = Field(..., description="LLM 生成的智能解析")

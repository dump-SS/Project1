"""板块二错题本 schema（对齐 openapi.yaml v1.6+ 错题本段）。

题本升格（D48）：错因（errorCause）+ 意图（intent）是**两个正交维度**——
- 错题 = 有错因标记；star 题 = 只有意图标记、无错因；
- 两者都进艾宾浩斯复习队列，但 **mastery 与归因只消费「有错因」的**；
- 返考措辞统一叫「复习 / 小测」，不叫「组卷」（用户会抵触）。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# 与契约 ErrorCause / ErrorIntent 枚举严格一致，不得另造取值
ERROR_CAUSES = (
    "concept_unclear",
    "calculation_error",
    "misreading",
    "careless",
    "knowledge_gap",
    "other",
)
ERROR_INTENTS = ("review", "good", "typical", "doubtful")


class ErrorRecordCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject: str
    raw_text: str = Field(..., alias="rawText")
    student_answer: str | None = Field(None, alias="studentAnswer")
    correct_answer: str | None = Field(None, alias="correctAnswer")
    error_type: str | None = Field(None, alias="errorType")
    error_note: str | None = Field(None, alias="errorNote")
    point_ids: List[str] = Field([], alias="pointIds")
    # D48 两正交维度 + D49 来源考试
    error_cause: str | None = Field(None, alias="errorCause")
    intent: str | None = Field(None, alias="intent")
    source_exam_id: str | None = Field(None, alias="sourceExamId")


class ErrorRecordUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    error_type: str | None = Field(None, alias="errorType")
    error_note: str | None = Field(None, alias="errorNote", max_length=4000)
    status: str | None = None
    point_ids: List[str] | None = Field(None, alias="pointIds")
    error_cause: str | None = Field(None, alias="errorCause")
    intent: str | None = Field(None, alias="intent")
    # 传 null 表示清除关联；用 model_fields_set 区分「没传」与「显式传 null」
    source_exam_id: str | None = Field(None, alias="sourceExamId")


class LinkedPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    point_id: str = Field(..., alias="pointId")
    name: str | None = None
    confidence: float | None = None


class ErrorRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    error_id: str = Field(..., alias="errorId")
    subject: str
    raw_text: str = Field(..., alias="rawText")
    student_answer: str | None = Field(None, alias="studentAnswer")
    correct_answer: str | None = Field(None, alias="correctAnswer")
    error_type: str | None = Field(None, alias="errorType")
    error_note: str | None = Field(None, alias="errorNote")
    status: str
    points: List[LinkedPoint] = []
    created_at: str = Field(..., alias="createdAt")
    last_reviewed_at: str | None = Field(None, alias="lastReviewedAt")
    # D48 两正交维度 + D49 来源考试（均为可空；无错因 = star 题，不喂 mastery）
    error_cause: str | None = Field(None, alias="errorCause")
    intent: str | None = Field(None, alias="intent")
    source_exam_id: str | None = Field(None, alias="sourceExamId")


class ErrorBookList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[ErrorRecord]
    pagination: dict


class ErrorRecordDeleted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    deleted: bool
    error_id: str = Field(..., alias="errorId")


class ReviewSubmit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    recall_correct: bool = Field(..., alias="recallCorrect")


class ReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    correct: bool
    next_review_at: str = Field(..., alias="nextReviewAt")
    interval_days: int = Field(..., alias="intervalDays")

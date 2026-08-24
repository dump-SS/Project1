"""板块二错题本 schema（对齐 openapi.yaml v1.5 错题本段）。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ErrorRecordCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject: str
    raw_text: str = Field(..., alias="rawText")
    student_answer: str | None = Field(None, alias="studentAnswer")
    correct_answer: str | None = Field(None, alias="correctAnswer")
    error_type: str | None = Field(None, alias="errorType")
    error_note: str | None = Field(None, alias="errorNote")
    point_ids: List[str] = Field([], alias="pointIds")


class ErrorRecordUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    error_type: str | None = Field(None, alias="errorType")
    error_note: str | None = Field(None, alias="errorNote", max_length=4000)
    status: str | None = None
    point_ids: List[str] | None = Field(None, alias="pointIds")


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

"""板块二知识库 schema（对齐 docs/openapi.yaml v1.5 学科知识库/错题本/掌握/复盘段）。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSubject(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject_code: str = Field(..., alias="subjectCode")
    name: str
    grade_band: str | None = Field(None, alias="gradeBand")
    point_count: int = Field(..., alias="pointCount")
    version: str


class KnowledgeSubjectList(BaseModel):
    items: List[KnowledgeSubject]


class KnowledgePoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    point_id: str = Field(..., alias="pointId")
    subject_code: str = Field(..., alias="subjectCode")
    code: str
    name: str
    definition: str
    parent_id: str | None = Field(None, alias="parentId")
    difficulty: int
    exam_weight: float = Field(..., alias="examWeight")
    error_tip: str | None = Field(None, alias="errorTip")


class KnowledgePointList(BaseModel):
    items: List[KnowledgePoint]


class KnowledgePointRelation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    src_point_id: str = Field(..., alias="srcPointId")
    dst_point_id: str = Field(..., alias="dstPointId")
    type: str
    weight: float | None = None


class KnowledgePointDetail(KnowledgePoint):
    relations: List[KnowledgePointRelation] = []


class KnowledgeGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject_code: str = Field(..., alias="subjectCode")
    nodes: List[KnowledgePoint]
    edges: List[KnowledgePointRelation]


class KnowledgePointMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    point_id: str = Field(..., alias="pointId")
    name: str
    subject_code: str = Field(..., alias="subjectCode")
    confidence: float
    matched_by: str = Field(..., alias="matchedBy")


class KnowledgePointMatchList(BaseModel):
    items: List[KnowledgePointMatch]
    matched_by: str = Field(..., alias="matchedBy")


class KnowledgeSummaryCreate(BaseModel):
    """知识复盘结构化入参。"""

    model_config = ConfigDict(populate_by_name=True)

    subject: str
    period: str

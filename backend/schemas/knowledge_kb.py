"""板块二知识库 schema（对齐 docs/openapi.yaml v1.5 学科知识库/错题本/掌握/复盘段）。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """知识点详情：基础字段 + 内容字段（讲解/频次/典型错误/例题/关键词/模块/教材）。

    typical_errors / keywords 在 ORM 层是 JSON 数组文本，经 validators 反序列化为 list。
    """
    relations: List[KnowledgePointRelation] = []

    explanation: str | None = None
    frequency: int | None = None
    typical_errors: List[str] | None = Field(default=None, alias="typicalErrors")
    example: str | None = None
    keywords: List[str] | None = Field(default=None, alias="keywords")
    module_path: str | None = Field(default=None, alias="modulePath")
    source_version: str | None = Field(default=None, alias="sourceVersion")

    @field_validator("typical_errors", "keywords", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        # ORM 列是 JSON 数组文本；已是 list 则原样返回
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:  # noqa: BLE001 — 脏数据回退空列表
                return []
        return []


class KnowledgeGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject_code: str = Field(..., alias="subjectCode")
    nodes: List[KnowledgePoint]
    edges: List[KnowledgePointRelation]
    weak_point_ids: List[str] = Field(default_factory=list, alias="weakPointIds")


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

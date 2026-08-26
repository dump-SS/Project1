"""板块二 ORM 模型（PRD 12.4 / gap 清单 §3.1）。

新增 8 张表（全部 kb_ 前缀，与板块一共享 data.db）：
- kb_subjects           学科（enabled 过滤）
- kb_points             知识点（parent_id 构树）
- kb_point_relations    概念关系（4 类）
- kb_errors             错题（软删 deleted_at；原文只本地，永不出域）
- kb_error_points       错题↔知识点关联（多对多 + 置信度）
- kb_point_mastery      user×point 掌握度
- kb_review_logs        复习日志（艾宾浩斯间隔由它驱动）
- kb_embeddings         向量引用（向量本体在本地向量库，表只存引用）

约定沿用 models/__init__.py：id 统一 String(64) 应用层生成；
时间字段 server_default=func.now()；user_id 冗余便于行级过滤。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# 知识点 JSON 内容列编解码（typical_errors / keywords 存 JSON 数组文本）
def db_json_to_list(raw: str | None) -> list[str]:
    """把 ORM 列里的 JSON 数组文本反序列化为 list；None/非法回退空列表。"""
    if not raw:
        return []
    try:
        import json
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except Exception:  # noqa: BLE001 — 脏数据降级空列表
        return []


def db_list_to_json(values: list[str]) -> str:
    """list → JSON 数组文本（存 String 列）。"""
    import json
    return json.dumps(values, ensure_ascii=False)


class KnowledgeSubject(Base):
    """学科（kb_subjects）。enabled=true 才可查。"""

    __tablename__ = "kb_subjects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(16), nullable=True)  # junior/senior
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class KnowledgePoint(Base):
    """知识点（kb_points）。parent_id 自关联构树；id 为 kp_ 前缀。"""

    __tablename__ = "kb_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    error_tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1-5
    exam_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)  # 0-1
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 知识点库内容字段（2026-08-25 建表；typical_errors/keywords 存 JSON 数组文本）
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)  # 讲解（80-200 字）
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3)  # 频次 1-5
    typical_errors: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
    example: Mapped[str | None] = mapped_column(Text, nullable=True)  # 例题（[仿题]开头）
    keywords: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
    module_path: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 模块路径
    source_version: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 教材全称（人教A版2019）


class KnowledgePointRelation(Base):
    """概念关系（kb_point_relations）。type ∈ prerequisite/derived/contrast/applied_in。"""

    __tablename__ = "kb_point_relations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    src_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dst_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)


class ErrorRecord(Base):
    """错题（kb_errors）。原文只本地，永不出域（EgressGuard knowledge_raw）。"""

    __tablename__ = "kb_errors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)  # ≤4000 字
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open/resolved
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 软删


class ErrorPoint(Base):
    """错题↔知识点关联（kb_error_points），多对多 + 置信度。"""

    __tablename__ = "kb_error_points"
    __table_args__ = (UniqueConstraint("error_id", "point_id", name="uq_error_point"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    error_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    point_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class PointMastery(Base):
    """知识点掌握度（kb_point_mastery）。联合唯一 (user_id, point_id)。"""

    __tablename__ = "kb_point_mastery"
    __table_args__ = (UniqueConstraint("user_id", "point_id", name="uq_user_point"),)

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReviewLog(Base):
    """复习日志（kb_review_logs）。艾宾浩斯间隔（1/2/4/7/15）由 recall_correct 驱动。"""

    __tablename__ = "kb_review_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    error_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    recall_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EmbeddingRef(Base):
    """向量引用（kb_embeddings）。向量本体存本地向量库，这里只存引用。"""

    __tablename__ = "kb_embeddings"

    vector_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)  # error/point
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

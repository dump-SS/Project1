"""考试（exams）——D49 独立实体。

对应 openapi.yaml `components.schemas.Exam / ExamCreate / ExamUpdate / ExamList`。
归属 C 板块（计划、目标、考试、计时与学习记录）。

设计要点（D49）：
- 考试是**独立实体，不是 Goal 的一种**；Goal 通过 `exam_id` + `target_score` 引用它，
  避免两套平行的目标体系。
- `score` 可空——考后回填，回填前为 null。成绩是唯一能把「自评」与「实际」对上的
  客观数据，回填后喂状态评估与画像。
- 错题可标来源考试（`kb_errors.source_exam_id`）。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Exam(Base):
    """考试。user_id 指向稳定 users.id（D59）。"""

    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 得分可空：考后回填，回填前 null（不做 0 值兜底，0 分与未回填是两回事）
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    full_score: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

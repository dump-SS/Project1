"""
Recommendation：个性化建议

对应 openapi.yaml：
  - POST   /recommendations                  → RecommendationCreate
  - GET    /recommendations / /{id}          → 列表 / 详情
  - PUT    /recommendations/{id}/feedback     → RatingFeedback

items 列表（title + content）以及 feedback 用 JSON 字符串存储；
generation.source 默认 llm，失败时降级为 template（schema 描述）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    scene: Mapped[str] = mapped_column(String(16), nullable=False)  # post_session / weekly_review
    subject: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    # 异步生成状态
    generation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    generation_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # llm / template
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 建议内容：JSON 列表 [ { title: str, content: str } ]
    items: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 生成依据（PRD 6.5 留痕）
    based_on_assessment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    based_on_record_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learning_records.id", ondelete="SET NULL"), nullable=True
    )
    based_on_state_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    based_on_explain: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 反馈（PUT 覆盖）
    feedback_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)  # useful/neutral/not_useful
    feedback_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feedback_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关联的 record（场景为 post_session 时记录学习记录 id）
    record_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("learning_records.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

"""
Summary：学习总结与复盘

对应 openapi.yaml：
  - POST /summaries                 → SummaryCreate
  - GET  /summaries / /{id}         → 列表 / 详情
  - PUT  /summaries/{id}/feedback    → RatingFeedback

复盘不做模板兜底（PRD 5.4 不展示半成品），失败即 failed；
content 4 个字段（overview/patterns/suggestions/encouragement）平铺成列。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 异步生成状态
    generation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    generation_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # content：失败/数据不足时整段为 null
    content_overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_patterns: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 列表
    content_suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 列表
    content_encouragement: Mapped[str | None] = mapped_column(Text, nullable=True)

    # dataPoints
    data_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_subjects: Mapped[str | None] = mapped_column(String(256), nullable=True)  # JSON 列表
    data_plan_completion_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_referenced_assessment_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)  # JSON
    data_min_required: Mapped[int | None] = mapped_column(Integer, nullable=True)

    message: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # 反馈
    feedback_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feedback_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feedback_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

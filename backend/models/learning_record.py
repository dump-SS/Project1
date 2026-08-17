"""
LearningRecord：学习记录

对应 openapi.yaml：
  - POST   /learning-records                       → RecordInput（创建时同步重算 assessment + 创建 recommendation）
  - GET    /learning-records                       → LearningRecordList
  - DELETE /learning-records/{recordId}            → 删除并触发重算

behavior / selfReport 字段比较多，按 schema 平铺成列（不嵌 JSON），便于 SQL 聚合查询；
note 是可选 ≤100 字备注，单独成列。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    subject: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-600

    plan_task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("plan_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # behavior 行为数据
    behavior_completion: Mapped[str] = mapped_column(String(16), nullable=False)  # completed/partial/abandoned
    behavior_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1
    behavior_interruptions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    behavior_blur_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # selfReport 自评数据
    self_report_focus: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    self_report_fatigue: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    self_report_emotion: Mapped[str] = mapped_column(String(16), nullable=False)  # positive/neutral/negative
    self_report_difficulty_feel: Mapped[str] = mapped_column(String(16), nullable=False)  # easy/moderate/hard

    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # ≤100 字
    skip_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

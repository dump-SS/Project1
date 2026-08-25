"""限流持久化表（PRD 6.4 / S0-T5）。

替代进程内 dict 的每日限流计数，重启不丢。
按 (user_id, bucket_key, bucket_date) 唯一，计数持久化到 SQLite。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"
    __table_args__ = (UniqueConstraint("user_id", "bucket_key", "bucket_date", name="uq_rate_limit_bucket"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bucket_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bucket_date: Mapped[date] = mapped_column(DateTime, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

"""限流持久化表（PRD 6.4 / S0-T5）。

替代进程内 dict 的每日限流计数，重启不丢。
按 (user_id, bucket_key, bucket_date) 唯一，计数持久化到 SQLite。

AuthRateLimit 是 auth 侧的限流与失败锁定（见 auth/rate_limit.py），
与上面按天计数的 RateLimitCounter 用途不同，故单列一张表。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
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


class AuthRateLimit(Base):
    """auth 限流 + 连续失败锁定（替代 auth/rate_limit.py 的进程内 dict）。

    scope 区分两种用途：
    - 'window'：窗口计数（如验证码 60s 频控）。count=窗口内已用次数，
      expires_at=窗口重置时刻，到期后计数归 1 重新计时
    - 'lock'：连续失败锁定。count=当前连续失败次数，expires_at=锁定解除时刻
      （0 表示累计中、尚未锁定）；达到 MAX_FAILS 时写入 expires_at 并清零 count

    expires_at 用**毫秒整数**，与 auth/rate_limit.py 的 time.time() * 1000 口径一致，
    避免 datetime 与时区/精度换算引入偏差。
    """
    __tablename__ = "auth_rate_limits"
    __table_args__ = (UniqueConstraint("scope", "bucket_key", name="uq_auth_rate_limit"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # 窗口类存业务 key（如 code:someone@example.com），锁定类存 email，
    # 最长取 email 上限 254 + 前缀余量
    bucket_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

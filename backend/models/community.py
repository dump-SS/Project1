"""板块三群体匿名参照 ORM 模型（M2/M3，PRD 10.2/10.3 + 决策方案 v1.7）。

独立命名空间，不改板块一/二原始表。三张表：
- community_features    个体特征行（匿名参与 ID，周期滚动物理删除）
- community_aggregates  聚合物化结果（分位数 + 直方图桶）
- community_audit_logs  授权/撤回/监护人联动审计（不含特征值，留存 6 个月）
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
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


class CommunityFeature(Base):
    """个体特征行。

    铁律：不含 user_id、不含原文/身份字段。anon_participant_id = HMAC(user_id, salt)
    不可反查；salt_version 支持 salt 轮换时按版本找回对应盐做撤回删除（§4.5）。
    特征行周期滚动后物理删除。
    """

    __tablename__ = "community_features"
    __table_args__ = (
        UniqueConstraint("anon_participant_id", "period", "metric", name="uq_community_feature"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    anon_participant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    salt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # ISO 周，如 2026-W35
    stage: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # junior/senior
    metric: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # hours/focus/fatigue/completion
    value: Mapped[float] = mapped_column(Float, nullable=False)  # 原始值（hours 小时 / focus 1-5 / completion 0-1）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CommunityAggregate(Base):
    """聚合物化表（M3）。subject 维度第一批不开放，维度 = metric × stage × period。"""

    __tablename__ = "community_aggregates"
    __table_args__ = (
        UniqueConstraint("period", "stage", "metric", name="uq_community_aggregate"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    pool_size: Mapped[int] = mapped_column(Integer, nullable=False)  # ≥ k
    percentiles: Mapped[str] = mapped_column(Text, nullable=False)  # JSON {p25,p50,p75}
    histogram: Mapped[str] = mapped_column(Text, nullable=False)  # JSON [{lo,hi,count}]（已做 count<n 合并）
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CommunityAuditLog(Base):
    """板块三审计留痕（§4.5：仅用户 ID/事件类型/时间戳，不含特征值，留存 6 个月）。

    user_id 仅存于审计表用于合规记录，不进入特征/聚合表。
    """

    __tablename__ = "community_audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False)  # consent_enable/consent_revoke/guardian_revoke
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

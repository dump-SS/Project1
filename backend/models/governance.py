"""pilot 运营与治理（usage_ledger / violation_logs / error_reports / medals）——G 板块。

对应 openapi.yaml `components.schemas.UsageLedgerEntry / ViolationLog / ErrorReport / Medal`。

设计要点：
- **usage_ledger 与 AICallLog 分两套，不合并**（#9）：AICallLog 刻意不带身份字段
  （合规去身份化），而按用户计量成本必须带身份。本表**只存数值，不存任何提示词或
  输出内容**。绝不给 AICallLog 补身份字段。
- 违规分级处置必须留痕（#43）：1 次警告 → 3 次临时封禁 → 永久。
- 报错两处入口（#46）：设置常驻 + 每条模型输出旁的消息级按钮；消息级必须带上下文，
  但上下文里**不含对话原文流水**（与 D45 原文短期留存口径分开）。
- 奖章只做最小版（#49）：3–5 个里程碑，不做积分商城 / 排行榜
  （排行榜与「社区不做社交」冲突）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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


class UsageLedger(Base):
    """按用户记录模型数值成本（pilot 不收费，但为定价留数据）。"""

    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 功能档位（chat / search / explain / embedded / multimodal），用于分档定价
    feature_tier: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 推理等级（#33：quick / standard / deep），与 credits 扣费档位绑定
    reasoning_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )


class ViolationLog(Base):
    """违规处置留痕（分级：warn / temp_ban / perm_ban）。"""

    __tablename__ = "violation_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 累计违规等级（1 起）：1 次警告 → 3 次临时封禁 → 永久
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # warn/temp_ban/perm_ban
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )


class ErrorReport(Base):
    """用户报错（#46）。context_json 只放结构化上下文，不放对话原文流水。"""

    __tablename__ = "error_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 消息级报错才有；设置常驻入口为 NULL
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 该条消息的意图判定结果（便于定位问题）
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )


class Medal(Base):
    """虚拟奖章最小版（#49）。同一里程碑只授予一次。"""

    __tablename__ = "medals"
    __table_args__ = (UniqueConstraint("user_id", "milestone", name="uq_user_medal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # first_record / streak_7_days / first_summary / first_goal_achieved / first_topic_book
    milestone: Mapped[str] = mapped_column(String(32), nullable=False)

    awarded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

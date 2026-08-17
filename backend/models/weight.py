"""AI 调权相关 ORM 模型（PRD 5.2 第 4 点 / 6.5）。

权重表（UserWeightConfig）+ 调权留痕（WeightAdjustLog）。
PRD 硬限制：α/β ∈ [0.3, 0.7]，子项 ∈ [0.1, 0.5]，单次变动 ≤ 0.1，
失败回退到当前权重（不是初始值）。这些都由 state_engine.weights.validate_adjustment 强制校验。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class UserWeightConfig(Base):
    """用户级权重表（PRD 7 信息架构）。

    权重存后台配置 + 用户级权重表，不写死在代码逻辑里。
    初始值：α=β=0.5，各子项等权 1/3。
    """
    __tablename__ = "user_weight_configs"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # α/β 主权重（行为子分 vs 自评子分）
    alpha: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    beta: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # 行为子项（完成度 / 正确率 / 节奏稳定度）
    w1: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)
    w2: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)
    w3: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)

    # 自评子项（专注度 / 反向疲劳 / 情绪正向）
    w4: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)
    w5: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)
    w6: Mapped[float] = mapped_column(Float, nullable=False, default=1 / 3)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WeightAdjustLog(Base):
    """每次调权留痕（PRD 5.2：支持回溯与人工回滚）。

    记录调整前后权重、模型给出的理由、是否发生越界回退、生效时间。
    """
    __tablename__ = "weight_adjust_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 调整前权重（快照）
    before_alpha: Mapped[float] = mapped_column(Float, nullable=False)
    before_beta: Mapped[float] = mapped_column(Float, nullable=False)
    before_w1: Mapped[float] = mapped_column(Float, nullable=False)
    before_w2: Mapped[float] = mapped_column(Float, nullable=False)
    before_w3: Mapped[float] = mapped_column(Float, nullable=False)
    before_w4: Mapped[float] = mapped_column(Float, nullable=False)
    before_w5: Mapped[float] = mapped_column(Float, nullable=False)
    before_w6: Mapped[float] = mapped_column(Float, nullable=False)

    # 调整后权重（快照）
    after_alpha: Mapped[float] = mapped_column(Float, nullable=False)
    after_beta: Mapped[float] = mapped_column(Float, nullable=False)
    after_w1: Mapped[float] = mapped_column(Float, nullable=False)
    after_w2: Mapped[float] = mapped_column(Float, nullable=False)
    after_w3: Mapped[float] = mapped_column(Float, nullable=False)
    after_w4: Mapped[float] = mapped_column(Float, nullable=False)
    after_w5: Mapped[float] = mapped_column(Float, nullable=False)
    after_w6: Mapped[float] = mapped_column(Float, nullable=False)

    # 模型返回的理由（PRD 6.5 可解释性）
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # 是否发生越界回退（模型返回值越界时，回退到当前权重而不是初始值）
    reverted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revert_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # 生效时间
    effective_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

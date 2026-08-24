"""AICallLog：LLM 调用与出域拦截留痕（PRD 6.5 / 6.4）。

铁律：本表不得存储用户身份信息（PRD §7：AICallLog 中不得存完整用户身份）。
仅记录功能类型、data_class、耗时、成功与否、是否被出域拦截、错误摘要、成本计量，
供成本监控（6.4）与问题回溯（6.5）使用。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AICallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 功能类型：weight_tuning / suggestion / summary / knowledge_summary / error_parse ...
    function_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 出域数据类：state_plan / knowledge_aggregated / knowledge_raw / None（未声明）
    data_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 出域 payload 摘要（hash 或字段名清单，不含原文；超长截断）
    input_digest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    egress_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

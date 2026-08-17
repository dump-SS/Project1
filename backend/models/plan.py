"""
Plan / PlanTask：学习计划 + 计划任务

对应 openapi.yaml：
  - POST   /plans                                     → PlanCreate
  - GET    /plans / /plans/{planId}                   → 列表 / 详情
  - PATCH  /plans/{planId}/tasks/{taskId}             → PlanTaskUpdate

adaptedFrom 字段（基于哪次状态评估做了强度调整）以 4 列形式平铺，避免 JSON；
新用户无历史数据时 4 列都为 NULL（schema 允许整体为 null）。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # 10-600

    # adaptedFrom：本次计划基于哪次状态评估做了强度调整
    adapted_from_assessment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapted_from_state_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adapted_from_adjustment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapted_from_note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class PlanTask(Base):
    __tablename__ = "plan_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    subject: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 数字越小越靠前
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    goal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # 任务调整相关（PATCH 写入）
    removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

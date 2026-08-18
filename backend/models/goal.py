"""
Goal：学习目标

对应 openapi.yaml：
  - POST   /goals              → GoalCreate
  - GET    /goals              → GoalList（含进度）
  - PATCH  /goals/{goalId}     → GoalUpdate（归档代替删除）

归档状态：active / archived（取自 schema description）
进度字段直接存为三列，避免 JSON 拆字段；前端的 ratio = completedTasks / plannedTasks
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # short_term / long_term
    subject: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)  # ≤50 字
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)  # ≤200 字
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    # 归档终态（仅 status=archived 时有值）：achieved / abandoned / expired
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 归档完成总结（≤200 字）
    completion_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    planned_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

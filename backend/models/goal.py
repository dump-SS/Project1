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

from sqlalchemy import Date, DateTime, Float, Integer, String, func
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
    # 板块二：目标绑定知识点 ID（v2.2，JSON 列表，可空）
    point_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 目标树父子关系（D6/D29）：长期目标下挂多个短期子目标。顶层目标为 NULL。
    # ⚠️ 不塞进 status 的 enum——active/archived 被 ?status= 过滤依赖，加平行字段才不波及他人。
    parent_goal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 考试引用（D49）：用 exam_id + target_score 表达「这次考到 X 分」，
    # 避免与 exams 形成两套平行的目标体系。
    exam_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    planned_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

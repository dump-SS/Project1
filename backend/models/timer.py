"""计时会话与分段（timer_sessions / timer_segments）—— C 板块。

对应 openapi.yaml `components.schemas.TimerSession / TimerSegment` 系列。

为什么必须有这两张表（§3.6 / D30 / D31 / #14）：
- **服务端持久化「进行中的计时会话」**：`started_at` + `mode` + `target_minutes` + 计划引用
  存服务端，前端只是视图。回来按**真实经过时间**恢复，根治「路由 state 丢失」技术债
  （现状 `/study-timer` 靠 navigate(state) 传参，刷新或直链就丢上下文）。
- **双模式**：countdown（有目标时长）/ countup（不限时）。恢复按 mode 分支：
  countdown → 剩余 = target − 已过；countup → 累计 = now − started_at。
- **僵尸治理**：只留「结束」一个出口（不做挂起）；倒计时到点后仍未结束 → 时长封顶 target；
  正计时超上限 → 判异常、截断，回来弹**恢复裁决卡**（不自动记账）。
- **有效时长 ≠ 墙上时长**：`effective_seconds` 只记可信时长，异常时必须用户核实。
- **分段计时（#14）**：一个会话下挂多个时间段，每段标注属于哪个任务，
  **结束只走一次收尾**（底线：不允许并行计时）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TimerSession(Base):
    """计时会话（一条「进行中」记录 = 专注态的唯一真相源）。"""

    __tablename__ = "timer_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # countdown（倒计时，有目标时长）/ countup（正计时，不限时）
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # 仅 countdown 有；countup 为 NULL
    target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 计划/任务/学科引用（D4 任务卡、D16 锚定回溯都靠它）
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    # running / finished（正常收尾）/ abandoned（僵尸裁决后丢弃）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 有效时长（秒）：倒计时 = min(经过, target)；正计时异常时需用户核实后才写入。
    # ⚠️ 不直接用 ended_at - started_at，那是「墙上时长」。
    effective_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 最近一次心跳（前端定时上报 / 任意交互时刷新）：僵尸判定与「异常会话」识别依据
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TimerSegment(Base):
    """计时会话内的一个时间段（#14 分段计时）。

    一个会话可挂多段，每段标注所属任务；**结束只走一次收尾**。
    """

    __tablename__ = "timer_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 本段属于哪个任务（切换任务即新开一段）
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 本段有效秒数（与 session.effective_seconds 同口径，不记墙上时长）
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

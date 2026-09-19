"""邀请码（invite_codes）——A 板块 / #50。

对应 openapi.yaml `components.schemas.InviteCode`。

设计要点：pilot 期邀请码注册，**一码一用**（可追踪发给谁 / 哪批）。
`used_by` 存使用者稳定 user_id（D59），不存邮箱——改邮箱不影响溯源。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    # 邀请码本身即主键（人可读短码，由 A 板块生成）
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 使用者稳定 user_id；未使用为 NULL（一码一用，用了就不再为空）
    used_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

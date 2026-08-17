"""Auth ORM 模型：auth_users / auth_codes / auth_sessions。

从 mock-server 迁移过来，表结构与 mock-server 的 users/codes/sessions 对齐，
便于后续数据迁移（直接导数据即可）。

注意：auth_users 与业务 users 表分离——auth_users 存邮箱+密码哈希（认证用），
users 表存学段/年级/学科（业务资料），用 email 作为关联键。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuthUser(Base):
    """认证用户（邮箱 + 密码哈希）。对应 mock-server 的 users 表。"""

    __tablename__ = "auth_users"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)  # scrypt: salt:hash
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AuthCode(Base):
    """验证码（注册/登录/重置密码三类，6位数字，5分钟有效）。

    对应 mock-server 的 codes 表。type ∈ {register, login, reset}。
    code 存 SHA256 哈希（不存明文）。
    """

    __tablename__ = "auth_codes"

    type: Mapped[str] = mapped_column(String(16), primary_key=True)  # register/login/reset
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)  # 毫秒时间戳


class AuthSession(Base):
    """会话（HttpOnly Cookie sid → email）。

    对应 mock-server 的 sessions 表。token_hash 存 SHA256(sid)。
    expires_at 是毫秒时间戳。
    """

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)  # 毫秒时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

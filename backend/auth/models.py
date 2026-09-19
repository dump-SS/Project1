"""Auth ORM 模型：auth_users / auth_codes / auth_sessions。

从 mock-server 迁移过来，表结构与 mock-server 的 users/codes/sessions 对齐，
便于后续数据迁移（直接导数据即可）。

注意：auth_users 与业务 users 表分离——auth_users 存邮箱+密码哈希（认证用），
users 表存学段/年级/学科（业务资料）。

稳定 ID 改造（D59）后，两表用 **user_id** 关联（不再用 email）：
- auth_users.user_id → users.id（内部主键，永不变）
- auth_users.email 降为**登录凭证**（唯一约束仍在，但可改可换绑）
- auth_sessions 存 user_id，不再存 email

这样改邮箱只动 auth_users.email + users.email 两列，users.id 不动，
所有业务数据自动保留（改造前改邮箱 = 换主键 = 全表外键更新）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuthUser(Base):
    """认证用户（邮箱 + 密码哈希 + 指向业务用户的稳定 ID）。"""

    __tablename__ = "auth_users"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    # 指向 users.id 的稳定 ID。可空仅为兼容「注册前先建认证行」之外的边缘场景
    # （测试直接造 AuthUser 等）；正常注册流程必填。
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
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
    # ⚠️ 毫秒时间戳（约 1.7e12）必须用 BigInteger：int32 上限 2147483647 会溢出。
    # SQLite 的 INTEGER 是动态宽度所以本地一直没暴露，Postgres（Neon）上会直接报错。
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AuthSession(Base):
    """会话（HttpOnly Cookie sid → 稳定 user_id）。

    对应 mock-server 的 sessions 表。token_hash 存 SHA256(sid)。
    expires_at 是毫秒时间戳。

    D59：存的是 **user_id**（不是 email）——会话不再随改邮箱而失效/串号。
    """

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 毫秒时间戳，同 AuthCode：必须 BigInteger，否则 Postgres 溢出
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

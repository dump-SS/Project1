"""
User / Settings / GuardianAuthorization

对应 openapi.yaml：
  - User                GET /me, PUT /me, PATCH /me
  - UserProfilePut/Patch PUT/PATCH /me 的请求体
  - Settings            GET/PATCH /me/settings
  - GuardianAuthorizationRequest  POST /me/guardian-authorization
  - /guardian-authorization/confirm  GET（公开，监护人点链接确认）

监护人状态：active / pending / revoked（不暴露在 openapi，由 SettingsUpdate 守门）
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    """当前用户资料（userId 由后端生成并写回）。

    三层身份（D59）：
      - `id`（内部主键，永不变）——所有业务表外键指向它，与登录凭证解耦；
      - `email`（登录凭证，可改可换绑）——仅认证与展示，**不作为身份**；
      - `handle`（对外标识，可选）——展示用，不暴露邮箱。

    改造前 `id` 里实际填的是邮箱（改邮箱 = 换主键 = 全表外键更新），
    pilot 删档期已按新 schema 重建，不做存量迁移。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 登录凭证邮箱：可空（测试/联调可用 X-User-ID 造无凭证用户），唯一索引防重复注册
    email: Mapped[str | None] = mapped_column(
        String(254), nullable=True, unique=True, index=True
    )
    # 对外标识：默认不生成（避免用真名/邮箱前缀，未成年保护），用户可自设
    handle: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)  # junior / senior
    grade: Mapped[str] = mapped_column(String(32), nullable=False)  # 自由文本，如 "高二"
    subjects: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Settings(Base):
    """用户设置。aiWeightTuningEnabled / sendTextToAI 默认值对齐 PRD 5.2 与 6.2。"""

    __tablename__ = "settings"

    user_id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )  # 1:1 with User.id（不建 FK，省得删用户时麻烦）
    ai_weight_tuning_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    send_text_to_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    knowledge_ai_egress_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 板块三：匿名聚合授权（默认关闭 + 每周自动参与选项，§4.7 决议）
    community_consent_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    community_auto_participate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GuardianAuthorization(Base):
    """监护人授权（PRD 8.1 合规底线）。

    status 取值：pending / active / revoked / expired
    """

    __tablename__ = "guardian_authorizations"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    guardian_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    confirm_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

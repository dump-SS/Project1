"""路由层共享依赖。

鉴权方式（auth 迁移后）：
- /auth/* 已从 mock-server 迁到 Python 后端，session 存 backend 自己的 auth_sessions 表
- current_user 解析 sid cookie → SHA256 查 auth_sessions → 拿到 email 作为 user_id
- 不再依赖 mock-server 的 data.db

current_user 读 ORM User 表返回真实资料（不再返 USER_MOCK 常量体）。
新用户（未建档）返回带 user_id 但 onboarding_completed=false 的桩，前端据此引导建档。
"""

from __future__ import annotations

import hashlib

from fastapi import Cookie, Header
from sqlalchemy.orm import Session

from auth.session import get_session
from database import SessionLocal
from models.user import GuardianAuthorization as GuardianAuthorizationORM
from models.user import User as UserORM
from schemas.user import GuardianAuthorizationInfo, User


def _build_user_response(db: Session, user_id: str) -> User:
    """从 ORM 组装 schema User（含 guardian 状态）。

    用户未建档时返回桩：user_id 真实，stage/grade/subjects 为默认值，
    onboarding_completed=false，前端据此引导建档。
    guardian 未提交时 status=pending（PRD 8.1：未授权视为待确认）。
    """
    user_row = db.get(UserORM, user_id)

    # 未建档：返回桩，引导前端跳建档页
    # subjects 给 ["other"] 占位（schema 要求 min_length=1），建档时覆盖
    if user_row is None:
        return User(
            userId=user_id,
            stage="senior",  # 默认值，建档时覆盖
            grade="",
            subjects=["other"],
            guardianAuthorization=GuardianAuthorizationInfo(status="pending"),
            onboardingCompleted=False,
        )

    # 已建档：读真实资料 + guardian 状态
    guardian_row = db.get(GuardianAuthorizationORM, user_id)
    if guardian_row is None:
        guardian_info = GuardianAuthorizationInfo(status="pending")
    else:
        guardian_info = GuardianAuthorizationInfo(
            status=guardian_row.status,
            expiresAt=guardian_row.expires_at.isoformat() if guardian_row.expires_at else None,
        )

    return User(
        userId=user_row.id,
        stage=user_row.stage,
        grade=user_row.grade,
        subjects=user_row.subjects or [],
        guardianAuthorization=guardian_info,
        onboardingCompleted=user_row.onboarding_completed,
    )


def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    sid: str | None = Cookie(default=None),
) -> User:
    """当前用户依赖。

    优先级：sid cookie（真实会话）> X-User-ID 头 > Bearer u_ > mock 用户。
    sid 现在查 backend 自己的 auth_sessions 表（不再查 mock-server data.db）。
    """
    db = SessionLocal()
    try:
        # 1. sid cookie（真实登录用户，查 auth_sessions 表）
        user_id = get_session(db, sid)

        # 2. X-User-ID 头（测试/联调显式指定）
        if user_id is None and x_user_id:
            user_id = x_user_id

        # 3. Bearer token 里以 u_ 开头的显式 userId（兼容旧测试）
        if user_id is None and authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token.startswith("u_"):
                user_id = token

        # 4. 无登录态 → 回落到 mock 用户（MVP 阶段允许匿名访问业务接口）
        if user_id is None:
            user_id = "u_10237"

        # 从 ORM 读真实资料（新用户返 onboarding_completed=false 桩）
        return _build_user_response(db, user_id)
    finally:
        db.close()

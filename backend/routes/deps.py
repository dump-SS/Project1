"""路由层共享依赖。"""
from __future__ import annotations

from fastapi import Header

from mock_data import USER_MOCK
from schemas.user import User


def _resolve_user_id(
    authorization: str | None,
    x_user_id: str | None,
) -> str:
    if x_user_id:
        return x_user_id

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("u_"):
            return token

    return USER_MOCK.user_id


def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> User:
    """当前用户依赖。

    MVP 阶段还没有 JWT 验签，先用显式 userId 让前端联调时能隔离用户数据。
    """
    user_id = _resolve_user_id(authorization, x_user_id)
    if user_id == USER_MOCK.user_id:
        return USER_MOCK
    return USER_MOCK.model_copy(update={"user_id": user_id})

"""路由层共享依赖。"""
from __future__ import annotations

from fastapi import Header

from mock_data import USER_MOCK
from schemas.user import User


def current_user(authorization: str | None = Header(default=None)) -> User:
    """MVP 阶段：从 Bearer token 解析出当前用户，mock 永远返回 USER_MOCK。

    真实实现：解析 JWT → 拿 userId → 查 User 表（步骤 3 接入）。
    """
    # 这里仅占位，不做实际校验，避免阻挡 Swagger UI 测试
    _ = authorization
    return USER_MOCK

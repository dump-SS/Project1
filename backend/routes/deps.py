"""路由层共享依赖。

鉴权方式（当前）：
- 前端登录走 mock-server（Node），签发 HttpOnly session cookie `sid`（7 天有效）。
- Python FastAPI 后端解析同一个 cookie：用 sha256(sid) 查 mock-server 的 SQLite sessions 表，
  拿到 email 作为真实 user_id。
- 这样业务接口不需要前端再传 token，浏览器自动带 cookie 即可。
- mock-server 的 sessions 表在 mock-server/data.db（与 backend/data.db 是两个独立文件）。

后续迁移 auth 到 Python 后端时，只需改这个 current_user 的实现，路由层不动。
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import Cookie, Header

from mock_data import USER_MOCK
from schemas.user import User

# mock-server 的 SQLite 文件路径（与 backend/data.db 分离）
_MOCK_SERVER_DB = Path(__file__).resolve().parent.parent.parent / "mock-server" / "data.db"


@contextmanager
def _mock_db_connection():
    """打开 mock-server 的 SQLite，只读查询 sessions 表。"""
    conn = sqlite3.connect(f"file:{_MOCK_SERVER_DB}?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()


def _resolve_user_id_from_sid(sid: str | None) -> str | None:
    """从 mock-server 的 sid cookie 解析出 email（作为 user_id）。"""
    if not sid:
        return None
    token_hash = hashlib.sha256(sid.encode()).hexdigest()
    try:
        with _mock_db_connection() as conn:
            row = conn.execute(
                "SELECT email, expires_at FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            email, expires_at = row
            # 过期 session 返回 None（mock-server 会删，但我们这里只读）
            import time
            if expires_at < int(time.time() * 1000):
                return None
            return email
    except sqlite3.Error:
        # mock-server 不在跑 / data.db 不存在 → 无法鉴权，返回 None 走 mock 用户
        return None


def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    sid: str | None = Cookie(default=None),
) -> User:
    """当前用户依赖。

    优先级：sid cookie（mock-server 真实会话）> X-User-ID 头 > Bearer u_ > mock 用户。
    这样前端登录后业务接口自动带上真实 email 作为 user_id，隔离用户数据。
    """
    # 1. mock-server session cookie（真实登录用户）
    user_id = _resolve_user_id_from_sid(sid)
    if user_id:
        return USER_MOCK.model_copy(update={"user_id": user_id})

    # 2. X-User-ID 头（测试/联调显式指定）
    if x_user_id:
        return USER_MOCK.model_copy(update={"user_id": x_user_id})

    # 3. Bearer token 里以 u_ 开头的显式 userId（mock-server 不签发，但保留兼容）
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("u_"):
            return USER_MOCK.model_copy(update={"user_id": token})

    # 4. 无登录态 → 回落到 mock 用户（MVP 阶段允许匿名访问业务接口）
    return USER_MOCK

"""Session 管理：创建、查询、销毁。

对应 mock-server/server.js 的 createSession / getSession / destroySession。
sid 是 32 字节随机 token，存 SHA256(sid) 到 DB，7 天有效。
Cookie 名 sid，HttpOnly，SameSite=Lax。
"""
from __future__ import annotations

import hashlib
import secrets
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuthSession

SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000  # 7 天
COOKIE_NAME = "sid"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_session(db: Session, email: str) -> tuple[str, str]:
    """创建会话。返回 (raw_sid, cookie_string)。

    raw_sid 用于 Set-Cookie，DB 只存 SHA256(sid)。
    """
    raw_sid = secrets.token_hex(32)  # 32 字节 = 64 hex 字符
    token_hash = _sha256(raw_sid)
    expires_at = int(time.time() * 1000) + SESSION_TTL_MS

    db.add(AuthSession(
        token_hash=token_hash,
        email=email,
        expires_at=expires_at,
    ))
    db.commit()

    max_age = SESSION_TTL_MS // 1000
    cookie = f"{COOKIE_NAME}={raw_sid}; HttpOnly; Path=/; SameSite=Lax; Max-Age={max_age}"
    return raw_sid, cookie


def get_session(db: Session, sid: str | None) -> str | None:
    """查会话。返回 email 或 None。

    过期会话自动删除。
    """
    if not sid:
        return None
    token_hash = _sha256(sid)
    row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalars().first()
    if row is None:
        return None
    if int(time.time() * 1000) > row.expires_at:
        db.delete(row)
        db.commit()
        return None
    return row.email


def destroy_session(db: Session, sid: str | None) -> str:
    """销毁会话。返回清空 cookie 的 Set-Cookie 值。"""
    if sid:
        token_hash = _sha256(sid)
        row = db.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        ).scalars().first()
        if row:
            db.delete(row)
            db.commit()
    return f"{COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def destroy_all_sessions_for_email(db: Session, email: str) -> None:
    """销毁某邮箱的所有会话（改密码时调用）。"""
    rows = db.execute(
        select(AuthSession).where(AuthSession.email == email)
    ).scalars().all()
    for r in rows:
        db.delete(r)
    db.commit()

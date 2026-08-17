"""验证码：生成、存储、校验、消费。

对应 mock-server/server.js 的 genCode / setCode / verifyCode / consumeCode。
验证码 6 位数字，5 分钟有效，存 SHA256 哈希。
"""
from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuthCode

CODE_TTL_MS = 5 * 60 * 1000  # 5 分钟


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gen_code() -> str:
    """6 位数字验证码。"""
    return str(random.randint(100000, 999999))


def store_code(db: Session, code_type: str, email: str) -> str:
    """生成验证码，存哈希到 DB，返回明文（供发邮件用）。

    同一 type+email 的验证码覆盖旧的（upsert）。
    """
    code = gen_code()
    code_hash = _sha256(code)
    expires_at = int(time.time() * 1000) + CODE_TTL_MS

    existing = db.execute(
        select(AuthCode).where(
            AuthCode.type == code_type, AuthCode.email == email
        )
    ).scalars().first()

    if existing:
        existing.code_hash = code_hash
        existing.expires_at = expires_at
    else:
        db.add(AuthCode(
            type=code_type, email=email,
            code_hash=code_hash, expires_at=expires_at,
        ))
    db.commit()
    return code


def verify_code(db: Session, code_type: str, email: str, code: str) -> tuple[bool, str]:
    """校验验证码。返回 (ok, msg)。不消费（消费调 consume_code）。"""
    row = db.execute(
        select(AuthCode).where(
            AuthCode.type == code_type, AuthCode.email == email
        )
    ).scalars().first()
    if row is None:
        return False, "请先获取验证码"
    if int(time.time() * 1000) > row.expires_at:
        return False, "验证码已过期"
    if not secrets_safe_eq(row.code_hash, _sha256(code)):
        return False, "验证码不正确"
    return True, ""


def consume_code(db: Session, code_type: str, email: str) -> None:
    """消费验证码（删除，一次性）。"""
    row = db.execute(
        select(AuthCode).where(
            AuthCode.type == code_type, AuthCode.email == email
        )
    ).scalars().first()
    if row:
        db.delete(row)
        db.commit()


def secrets_safe_eq(a: str, b: str) -> bool:
    """时序安全比较两个 hex 字符串。"""
    import secrets as _s
    try:
        return _s.compare_digest(bytes.fromhex(a), bytes.fromhex(b))
    except ValueError:
        return _s.compare_digest(a.encode(), b.encode())

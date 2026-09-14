"""限流 + 连续失败锁定（持久化到 auth_rate_limits 表）。

对应 mock-server/server.js 的 allow / isLocked / recordFail / clearFails。

早期是进程内 dict（_rate_buckets / _login_fails），单实例够用，但多实例部署下
每个实例各算各的——「连续失败 5 次锁定」会退化成 5×N 次，且进程重启计数清零。
现改为读写 SQLite，与 routes/community.py 的社区聚合限频同一套持久化思路
（pilot 阶段不引入 Redis）。

对外只暴露 allow / is_locked / record_fail / clear_fails 四个函数，签名与内存版
完全一致，调用方（routes/auth.py）零改动。

时间口径：一律用**毫秒整数**（time.time() * 1000），与内存版一致，
避免 datetime 换算引入时区/精度偏差。
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models.rate_limit import AuthRateLimit

MAX_FAILS = 5
LOCK_MS = 15 * 60 * 1000  # 锁定 15 分钟

# AuthRateLimit.scope 的两个取值，语义见 models/rate_limit.py
_SCOPE_WINDOW = "window"
_SCOPE_LOCK = "lock"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _find(db: Session, scope: str, bucket_key: str) -> AuthRateLimit | None:
    return (
        db.execute(
            select(AuthRateLimit).where(
                AuthRateLimit.scope == scope,
                AuthRateLimit.bucket_key == bucket_key,
            )
        )
        .scalars()
        .first()
    )


def allow(key: str, limit: int, window_ms: int) -> bool:
    """检查是否允许请求。允许则计数+1，超限返回 False。

    首次进入窗口即计 1 并放行；窗口到期后计数归 1 重新计时。
    """
    now = _now_ms()
    db = SessionLocal()
    try:
        row = _find(db, _SCOPE_WINDOW, key)
        if row is None:
            db.add(AuthRateLimit(
                id=f"arl_{uuid.uuid4().hex[:16]}",
                scope=_SCOPE_WINDOW,
                bucket_key=key,
                count=1,
                expires_at=now + window_ms,
            ))
            db.commit()
            return True

        if now >= row.expires_at:
            row.count = 1
            row.expires_at = now + window_ms
            db.commit()
            return True

        if row.count >= limit:
            return False

        row.count += 1
        db.commit()
        return True
    finally:
        db.close()


def is_locked(email: str) -> bool:
    """检查邮箱是否被锁定（连续失败 MAX_FAILS 次）。

    锁定到期后顺手删除记录，与内存版一致——否则过期记录会一直挂在表里。
    """
    now = _now_ms()
    db = SessionLocal()
    try:
        row = _find(db, _SCOPE_LOCK, email)
        if row is None:
            return False
        if row.expires_at and now < row.expires_at:
            return True
        if row.expires_at:
            db.delete(row)
            db.commit()
        return False
    finally:
        db.close()


def record_fail(email: str) -> None:
    """记录一次验证失败。累计到 MAX_FAILS 后锁定 LOCK_MS。"""
    db = SessionLocal()
    try:
        row = _find(db, _SCOPE_LOCK, email)
        if row is None:
            row = AuthRateLimit(
                id=f"arl_{uuid.uuid4().hex[:16]}",
                scope=_SCOPE_LOCK,
                bucket_key=email,
                count=0,
                expires_at=0,
            )
            db.add(row)

        row.count += 1
        if row.count >= MAX_FAILS:
            row.expires_at = _now_ms() + LOCK_MS
            row.count = 0
        db.commit()
    finally:
        db.close()


def clear_fails(email: str) -> None:
    """清除失败记录（验证成功后调用）。"""
    db = SessionLocal()
    try:
        row = _find(db, _SCOPE_LOCK, email)
        if row is not None:
            db.delete(row)
            db.commit()
    finally:
        db.close()


def reset_state(scope: str | None = None) -> None:
    """清空限流状态（测试辅助）。

    scope=None 清全部；"window" / "lock" 只清对应类别。
    内存版测试靠 _rate_buckets.clear() / _login_fails.clear() 重置，
    改为持久化后必须走这里，否则跨用例的残留会互相污染。
    """
    db = SessionLocal()
    try:
        query = db.query(AuthRateLimit)
        if scope is not None:
            query = query.filter(AuthRateLimit.scope == scope)
        query.delete()
        db.commit()
    finally:
        db.close()

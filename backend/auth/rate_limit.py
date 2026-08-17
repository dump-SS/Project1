"""限流 + 连续失败锁定（进程内存级）。

对应 mock-server/server.js 的 allow / isLocked / recordFail / clearFails。
MVP 阶段用进程内存（单实例够用），多实例部署需换 Redis。
"""
from __future__ import annotations

import time
from collections import defaultdict

# 限流桶：key -> {count, reset_at}
_rate_buckets: dict[str, dict] = {}

# 连续失败锁定：email -> {count, locked_until}
_login_fails: dict[str, dict] = defaultdict(lambda: {"count": 0, "locked_until": 0})

MAX_FAILS = 5
LOCK_MS = 15 * 60 * 1000  # 锁定 15 分钟


def allow(key: str, limit: int, window_ms: int) -> bool:
    """检查是否允许请求。允许则计数+1，超限返回 False。"""
    now = time.time() * 1000
    b = _rate_buckets.get(key)
    if not b or now >= b["reset_at"]:
        _rate_buckets[key] = {"count": 1, "reset_at": now + window_ms}
        return True
    if b["count"] >= limit:
        return False
    b["count"] += 1
    return True


def is_locked(email: str) -> bool:
    """检查邮箱是否被锁定（连续失败 5 次）。"""
    rec = _login_fails.get(email)
    if not rec:
        return False
    if rec["locked_until"] and time.time() * 1000 < rec["locked_until"]:
        return True
    if rec["locked_until"]:
        _login_fails.pop(email, None)
    return False


def record_fail(email: str) -> None:
    """记录一次验证失败。达到 MAX_FAILS 后锁定。"""
    rec = _login_fails[email]
    rec["count"] += 1
    if rec["count"] >= MAX_FAILS:
        rec["locked_until"] = time.time() * 1000 + LOCK_MS
        rec["count"] = 0


def clear_fails(email: str) -> None:
    """清除失败记录（验证成功后调用）。"""
    _login_fails.pop(email, None)

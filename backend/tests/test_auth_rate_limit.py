"""auth 限流持久化测试（进程内 dict → auth_rate_limits 表）。

验证重点：
- 计数与锁定状态落在表里：进程重启 / 多实例下不再各算各的
- 对外行为与内存版一致（阈值、放行/拒绝语义、过期清理）
- 函数签名未变，routes/auth.py 调用处零改动（由 tests/test_auth.py 覆盖）

「跨进程可见」的验证方式：不调函数、直接用另一个 Session 往表里写记录，
再断言函数能读到——等价于「另一个实例已经写入状态」。
"""
from __future__ import annotations

import time

from auth import rate_limit
from database import SessionLocal
from models.rate_limit import AuthRateLimit


def _seed(scope: str, bucket_key: str, count: int, expires_at: int) -> None:
    """直接往表里预置一行，模拟「另一个进程写下的状态」。"""
    db = SessionLocal()
    try:
        db.add(AuthRateLimit(
            id=f"arl_seed_{scope}",
            scope=scope,
            bucket_key=bucket_key,
            count=count,
            expires_at=expires_at,
        ))
        db.commit()
    finally:
        db.close()


def _rows(scope: str) -> list[AuthRateLimit]:
    db = SessionLocal()
    try:
        return db.query(AuthRateLimit).filter_by(scope=scope).all()
    finally:
        db.close()


# ---------- 窗口限流 ----------

def test_allow_counts_and_blocks_within_window():
    """窗口内达限即拒绝（limit=1 时第二次调用 False）。"""
    rate_limit.reset_state()
    key = "code:window@example.com"

    assert rate_limit.allow(key, 1, 60_000) is True
    assert rate_limit.allow(key, 1, 60_000) is False


def test_allow_window_resets_after_expiry():
    """窗口到期后计数归 1 重新放行。"""
    rate_limit.reset_state()
    key = "code:expire@example.com"

    assert rate_limit.allow(key, 1, 60_000) is True
    assert rate_limit.allow(key, 1, 60_000) is False

    # 把窗口重置时刻改到过去，模拟窗口到期
    db = SessionLocal()
    try:
        row = db.query(AuthRateLimit).filter_by(scope="window", bucket_key=key).one()
        row.expires_at = 0
        db.commit()
    finally:
        db.close()

    assert rate_limit.allow(key, 1, 60_000) is True


def test_window_state_is_read_from_table():
    """表里已有的计数会被读到——证明状态不在进程内存里。

    等价于「另一个实例已用掉配额」：本进程首次调用就应被拒。
    """
    rate_limit.reset_state()
    key = "code:shared@example.com"
    _seed("window", key, count=1, expires_at=int(time.time() * 1000) + 60_000)

    assert rate_limit.allow(key, 1, 60_000) is False


# ---------- 失败锁定 ----------

def test_lock_after_max_fails():
    """连续失败 MAX_FAILS 次才锁定，第 MAX_FAILS-1 次仍放行。"""
    rate_limit.reset_state()
    email = "lock@example.com"

    for _ in range(rate_limit.MAX_FAILS - 1):
        rate_limit.record_fail(email)
    assert rate_limit.is_locked(email) is False, "未达阈值不应锁定"

    rate_limit.record_fail(email)
    assert rate_limit.is_locked(email) is True, "达到阈值应锁定"


def test_lock_state_is_read_from_table():
    """另一个实例写入的锁定，本进程立即可见（内存版做不到）。"""
    rate_limit.reset_state()
    email = "shared-lock@example.com"
    _seed("lock", email, count=0, expires_at=int(time.time() * 1000) + 60_000)

    assert rate_limit.is_locked(email) is True


def test_clear_fails_releases_lock():
    """验证成功后清除失败记录，锁定解除。"""
    rate_limit.reset_state()
    email = "clear@example.com"

    for _ in range(rate_limit.MAX_FAILS):
        rate_limit.record_fail(email)
    assert rate_limit.is_locked(email) is True

    rate_limit.clear_fails(email)
    assert rate_limit.is_locked(email) is False


def test_expired_lock_is_cleaned():
    """锁定到期返回 False，并顺手删掉过期行（与内存版行为一致）。"""
    rate_limit.reset_state()
    email = "expired@example.com"
    _seed("lock", email, count=0, expires_at=int(time.time() * 1000) - 1)

    assert rate_limit.is_locked(email) is False
    assert _rows("lock") == [], "过期锁定行应被清理"


def test_fail_count_resets_after_lock():
    """锁定后计数清零：解锁后需要重新累计 MAX_FAILS 次。"""
    rate_limit.reset_state()
    email = "reset@example.com"

    for _ in range(rate_limit.MAX_FAILS):
        rate_limit.record_fail(email)

    db = SessionLocal()
    try:
        row = db.query(AuthRateLimit).filter_by(scope="lock", bucket_key=email).one()
        assert row.count == 0, "锁定后 count 应清零"
        assert row.expires_at > int(time.time() * 1000), "应写入未来的解锁时刻"
    finally:
        db.close()


# ---------- 契约与辅助 ----------

def test_thresholds_unchanged():
    """阈值常量与内存版完全一致（任务要求不得改动）。"""
    assert rate_limit.MAX_FAILS == 5
    assert rate_limit.LOCK_MS == 15 * 60 * 1000


def test_reset_state_is_scoped():
    """reset_state 可按 scope 单独清理，测试间互不污染。"""
    rate_limit.reset_state()
    rate_limit.allow("code:scope@example.com", 5, 60_000)
    rate_limit.record_fail("scope@example.com")

    rate_limit.reset_state("window")

    assert _rows("window") == []
    assert len(_rows("lock")) == 1

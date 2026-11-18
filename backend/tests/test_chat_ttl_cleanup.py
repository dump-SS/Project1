"""Chat 原文 TTL 清除 job 测试（D45：到期物理删除，未到期保留）。

共享 conftest 的测试库隔离 + 每用例清库规则。
"""
from datetime import datetime, timedelta

from jobs.chat_ttl_cleanup import cleanup_expired


def test_cleanup_expired_deletes_only_expired():
    from database import SessionLocal
    from models.chat import ChatRawMessage
    from sqlalchemy import func, select

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        # 已过期（30+ 天前到期）
        db.add(ChatRawMessage(
            id="msg_expired", user_id="ttl_1", session_id="s1", role="user",
            content="过期的原文", created_at=now - timedelta(days=35),
            expires_at=now - timedelta(days=5),
        ))
        # 未过期（30 天后到期）
        db.add(ChatRawMessage(
            id="msg_alive", user_id="ttl_1", session_id="s1", role="user",
            content="还活着的原文", created_at=now,
            expires_at=now + timedelta(days=30),
        ))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        stat = cleanup_expired(db)
    finally:
        db.close()

    assert stat["deleted"] == 1

    db = SessionLocal()
    try:
        remaining = db.execute(
            select(ChatRawMessage.id).where(ChatRawMessage.user_id == "ttl_1")
        ).scalars().all()
    finally:
        db.close()
    assert remaining == ["msg_alive"]   # 只有未过期的保留


# --------------------------------------------------------------- 调度器（真的在跑）


def test_scheduler_loop_calls_cleanup(monkeypatch):
    """调度循环必须真的调用清理函数——「有 job 文件」不等于「到期会删」。"""
    import asyncio

    from jobs import chat_ttl_cleanup as m

    calls: list[int] = []
    monkeypatch.setattr(
        m, "run_chat_ttl_cleanup", lambda: calls.append(1) or {"deleted": 0}
    )

    async def _run() -> None:
        task = asyncio.create_task(m._scheduler_loop())
        await asyncio.sleep(0)   # 让循环跑第一轮（立刻清一次），随后挂在 sleep 上
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
    assert calls, "调度循环没有调用 run_chat_ttl_cleanup"


def test_start_returns_task(monkeypatch):
    """start_* 返回可取消的 task（lifespan 关机时要 cancel 它）。"""
    import asyncio

    from jobs import chat_ttl_cleanup as m

    monkeypatch.setattr(m, "run_chat_ttl_cleanup", lambda: {"deleted": 0})

    async def _run() -> None:
        task = m.start_chat_ttl_cleanup_scheduler()
        assert task is not None, "start_chat_ttl_cleanup_scheduler 返回 None"
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


#: 每个「周期性 job」的（模块, 启动函数）。新增 job 必须同时挂进 lifespan，
#: 否则就是 2026-11-18 那个坑：job 写了、测试过了、但从来没被调度过。
EXPECTED_SCHEDULERS = [
    ("jobs.weekly_knowledge_summary", "start_weekly_summary_scheduler"),
    ("jobs.community_aggregate", "start_community_scheduler"),
    ("jobs.chat_ttl_cleanup", "start_chat_ttl_cleanup_scheduler"),
]


def test_all_job_schedulers_are_wired_in_lifespan():
    """静态守卫：lifespan 里既要 import 启动函数，也要真的调用它。

    2026-11-18 的合规缺口正是这个形态——`jobs/chat_ttl_cleanup.py` 有实现、
    有单测，`main.py` 却没挂调度，于是「30 天到期物理删除」的承诺一直没兑现，
    而所有测试都是绿的。靠 review 记性防不住，钉成断言。
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    missing = [
        f"{mod}.{fn}"
        for mod, fn in EXPECTED_SCHEDULERS
        if f"import {fn}" not in src or f"{fn}()" not in src
    ]
    assert not missing, (
        "以下 job 实现了但没挂进 main.py lifespan（到期不会执行）：\n  "
        + "\n  ".join(missing)
    )
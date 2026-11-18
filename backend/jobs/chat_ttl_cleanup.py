"""Chat 原文 TTL 清除 job（D45）。

对话原文短期留存：chat_raw_messages 写入时带 expires_at（RAW_TTL_DAYS=30，见 chat_engine）。
本 job 周期把 **已到期** 的原文**物理删除**——产品不可见、不留回看入口，到期即清，不给未成年产品留存量。

与 community / weekly 等 job 同风格：run_* 为后台入口（自开自关 session），内部函数可传入 session 便于测试。

⚠️ **实现了不等于在跑**（2026-11-18 实锤）：本文件早在 11 月就写好且有测试，
但 `main.py` 的 lifespan 一直只挂了 weekly / community 两个调度器，这个 job 从没被调度过
——到期原文实际一直留在库里，也就是「30 天物理删除」这条承诺没兑现。
修法是补 :func:`start_chat_ttl_cleanup_scheduler` 并挂进 lifespan；
`tests/test_chat_ttl_cleanup.py` 另加静态守卫，防止将来再加 job 又忘了挂。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import delete

from models.chat import ChatRawMessage

logger = logging.getLogger(__name__)

#: 清理周期。1 小时：到期即清的最坏滞后 1 小时，代价只是一条走索引的 DELETE。
CLEANUP_INTERVAL_SECONDS = 3600


def cleanup_expired(db) -> dict:
    """物理删除 expires_at 已到期的对话原文。返回 {deleted}。"""
    now = datetime.utcnow()
    result = db.execute(
        delete(ChatRawMessage).where(ChatRawMessage.expires_at < now)
    )
    db.commit()
    return {"deleted": result.rowcount}


def run_chat_ttl_cleanup() -> dict:
    """后台入口：自开 session 执行清理，异常不穿透（job 兜底返回 0）。"""
    from database import SessionLocal as SL

    db = SL()
    try:
        return cleanup_expired(db)
    except Exception:  # noqa: BLE001 — job 异常不穿透
        logger.exception("[CHAT] 原文 TTL 清理失败")
        return {"deleted": 0}
    finally:
        db.close()


async def _scheduler_loop() -> None:
    """启动后立即清一次（部署当天就能把积压的过期原文清掉），之后每小时一次。"""
    while True:
        try:
            stat = run_chat_ttl_cleanup()
            if stat.get("deleted"):
                logger.info("[CHAT] 原文 TTL 清理删除 %d 条", stat["deleted"])
        except Exception:  # noqa: BLE001 — 定时器绝不能因单次失败退出
            logger.exception("[CHAT] 原文 TTL 定时清理异常")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def start_chat_ttl_cleanup_scheduler() -> asyncio.Task | None:
    """FastAPI startup 调用；失败仅记日志，不阻断启动（与另外两个调度器同口径）。"""
    try:
        task = asyncio.create_task(_scheduler_loop())
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT] 启动原文 TTL 清理调度器失败")
        return None
    logger.info("[CHAT] 原文 TTL 清理调度器已启动（每 %d 秒）", CLEANUP_INTERVAL_SECONDS)
    return task
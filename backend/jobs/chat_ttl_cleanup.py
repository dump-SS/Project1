"""Chat 原文 TTL 清除 job（D45）。

对话原文短期留存：chat_raw_messages 写入时带 expires_at（RAW_TTL_DAYS=30，见 chat_engine）。
本 job 周期把 **已到期** 的原文**物理删除**——产品不可见、不留回看入口，到期即清，不给未成年产品留存量。

与 community / weekly 等 job 同风格：run_* 为后台入口（自开自关 session），内部函数可传入 session 便于测试。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete

from models.chat import ChatRawMessage

logger = logging.getLogger(__name__)


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
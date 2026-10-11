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
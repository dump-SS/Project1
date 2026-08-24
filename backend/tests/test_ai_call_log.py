"""AICallLog 持久化测试（W3-2，PRD 6.5）。

验证：
- log_call 正常写入（function_type/data_class/latency/success）
- egress 拦截写入 egress_blocked=1 且不含身份字段
- 写入失败不影响业务（表已建）
"""
from __future__ import annotations

from ai_call_log import log_call, log_egress_block


def test_log_call_persists():
    log_call(
        context={"scene": "knowledge_summary", "data_class": "knowledge_aggregated"},
        latency_ms=123,
        success=True,
    )
    from database import SessionLocal
    from models.ai_call_log import AICallLog
    from sqlalchemy import select

    db = SessionLocal()
    try:
        rows = db.execute(select(AICallLog)).scalars().all()
        assert len(rows) == 1
        r = rows[0]
        assert r.function_type == "knowledge_summary"
        assert r.data_class == "knowledge_aggregated"
        assert r.latency_ms == 123
        assert r.success is True
        assert r.egress_blocked is False
    finally:
        db.close()


def test_log_egress_block_persists_blocked_flag():
    log_egress_block(
        context={"scene": "error_parse", "data_class": "knowledge_raw"},
        reason="knowledge_raw 禁止出域",
    )
    from database import SessionLocal
    from models.ai_call_log import AICallLog
    from sqlalchemy import select

    db = SessionLocal()
    try:
        row = db.execute(
            select(AICallLog).where(AICallLog.egress_blocked.is_(True))
        ).scalars().first()
        assert row is not None
        assert row.success is False
        assert row.function_type == "error_parse"
    finally:
        db.close()


def test_no_identity_column():
    """AICallLog 不得存用户身份（PRD §7 铁律）。"""
    from models.ai_call_log import AICallLog
    cols = {c.name for c in AICallLog.__table__.columns}
    assert "user_id" not in cols
    assert "email" not in cols

"""限流持久化单测（S0-T5）。

验证：达限返回 429；计数持久化到 rate_limit_counters（重建 Session 后保留）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.rate_limit import RateLimitCounter

client = TestClient(app)

HDR = {"X-User-ID": "u_limit_test"}


def _invoke():
    return client.post("/api/v1/knowledge-summary", json={"subject": "math", "period": "本周"}, headers=HDR)


def test_rate_limit_persists_across_sessions():
    # 直接用持久层预置计数到上限（模拟达限）
    from datetime import datetime

    db = SessionLocal()
    try:
        db.query(RateLimitCounter).filter_by(user_id="u_limit_test").delete()
        db.add(RateLimitCounter(
            id="rl_persist_test",
            user_id="u_limit_test",
            bucket_key="knowledge_summary",
            bucket_date=datetime.utcnow(),
            count=1,  # 已达 config.rate_limit_summary_per_day=1
        ))
        db.commit()
    finally:
        db.close()

    # 新请求应被 429（计数来自持久层，而非进程内 dict）
    r = _invoke()
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"


def test_rate_limit_counter_increments():
    from datetime import datetime

    db = SessionLocal()
    try:
        db.query(RateLimitCounter).filter_by(user_id="u_limit_test").delete()
        db.commit()
    finally:
        db.close()

    # 首次请求应 200（或降级文案），并在持久层留下计数
    r = _invoke()
    assert r.status_code in (200, 202)

    db = SessionLocal()
    try:
        row = (
            db.query(RateLimitCounter)
            .filter_by(user_id="u_limit_test", bucket_key="knowledge_summary")
            .first()
        )
        assert row is not None
        assert row.count >= 1
    finally:
        db.close()

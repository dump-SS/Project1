"""板块三聚合接口集成测试（M3/M5）。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.community import CommunityAggregate, CommunityFeature
from models.user import Settings as SettingsORM

client = TestClient(app)

HDR = {"X-User-ID": "u_agg_test"}


def _seed_consent(enabled: bool):
    db = SessionLocal()
    try:
        s = db.get(SettingsORM, "u_agg_test")
        if s is None:
            s = SettingsORM(user_id="u_agg_test")
            db.add(s)
        s.community_consent_enabled = enabled
        db.commit()
    finally:
        db.close()


def _seed_aggregate(pool=25):
    from jobs.community_aggregate import _current_iso_week

    db = SessionLocal()
    try:
        period = _current_iso_week()
        db.add(CommunityAggregate(
            id="cagg_test",
            period=period,
            stage="senior",
            metric="hours",
            pool_size=pool,
            percentiles=json.dumps({"p25": 10.0, "p50": 20.0, "p75": 30.0}),
            histogram=json.dumps([
                {"lo": 8, "hi": 16, "count": 10},
                {"lo": 16, "hi": 24, "count": 10},
                {"lo": 24, "hi": None, "count": 5},
            ]),
        ))
        db.commit()
    finally:
        db.close()


def test_aggregate_requires_consent():
    _seed_consent(False)
    r = client.get("/api/v1/community/aggregate", params={"stage": "senior", "metric": "hours"}, headers=HDR)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "COMMUNITY_CONSENT_REQUIRED"


def test_aggregate_insufficient_pool_has_no_numbers():
    _seed_consent(True)
    # 无聚合行 → 503，响应体不含任何数值（§4.9）
    r = client.get("/api/v1/community/aggregate", params={"stage": "senior", "metric": "focus"}, headers=HDR)
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "COMMUNITY_INSUFFICIENT_POOL"
    assert "poolSize" not in body


def test_aggregate_returns_materialized_result():
    _seed_consent(True)
    _seed_aggregate(pool=25)
    r = client.get("/api/v1/community/aggregate", params={"stage": "senior", "metric": "hours"}, headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["poolSize"] == 25
    assert body["metric"] == "hours"
    assert body["percentiles"]["p50"] == 20.0
    assert len(body["histogram"]) >= 1


def test_aggregate_validation():
    _seed_consent(True)
    r = client.get("/api/v1/community/aggregate", params={"stage": "bad", "metric": "hours"}, headers=HDR)
    assert r.status_code == 400

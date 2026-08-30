"""板块三 M1 授权链路测试：GET/PUT /me/community-consent + 监护人联动。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.user import Settings as SettingsORM

client = TestClient(app)

HDR = {"X-User-ID": "u_comm_test"}


def _clean():
    db = SessionLocal()
    try:
        s = db.get(SettingsORM, "u_comm_test")
        if s is not None:
            db.delete(s)
        db.commit()
    finally:
        db.close()


def test_default_disabled():
    _clean()
    r = client.get("/api/v1/me/community-consent", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["autoParticipate"] is True


def test_enable_then_revoke():
    _clean()
    r = client.put("/api/v1/me/community-consent", json={"enabled": True}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    r2 = client.get("/api/v1/me/community-consent", headers=HDR)
    assert r2.json()["enabled"] is True

    r3 = client.put("/api/v1/me/community-consent", json={"enabled": False}, headers=HDR)
    assert r3.status_code == 200
    assert r3.json()["enabled"] is False


def test_enabled_requires_field():
    _clean()
    r = client.put("/api/v1/me/community-consent", json={}, headers=HDR)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"

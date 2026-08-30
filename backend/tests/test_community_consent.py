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


def test_revoke_physically_deletes_features():
    """P0 回归：撤回后该用户特征行物理删除（按 anon_participant_id）。"""
    from anon_id import compute_anon_id
    from models.community import CommunityFeature

    # 预置特征行（模拟授权用户已抽取的特征）
    anon = compute_anon_id("u_comm_test")
    db = SessionLocal()
    try:
        s = db.get(SettingsORM, "u_comm_test")
        if s is None:
            s = SettingsORM(user_id="u_comm_test")
            db.add(s)
        s.community_consent_enabled = True
        db.add(CommunityFeature(
            id="cf_revoke_test",
            anon_participant_id=anon,
            salt_version=0,
            period="2026-W99",
            stage="senior",
            metric="hours",
            value=12.0,
        ))
        db.commit()
    finally:
        db.close()

    # 撤回
    r = client.put("/api/v1/me/community-consent", json={"enabled": False}, headers=HDR)
    assert r.status_code == 200

    # 特征行应被物理删除
    db = SessionLocal()
    try:
        n = db.query(CommunityFeature).filter(CommunityFeature.anon_participant_id == anon).count()
        assert n == 0
    finally:
        db.close()

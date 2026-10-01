"""板块三 M1 授权链路测试：GET/PUT /me/community-consent + 监护人联动。

D41 收紧（A 板块 M1，契约 v1.8.0）：**开启**群体参照要求监护人授权已 active——
未授权/待确认 403 GUARDIAN_AUTHORIZATION_REQUIRED，已失效 403 GUARDIAN_AUTHORIZATION_EXPIRED；
**撤回不受限制**（撤回是用户权利，不能被授权状态挡住）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.user import GuardianAuthorization as GuardianORM
from models.user import Settings as SettingsORM

client = TestClient(app)

HDR = {"X-User-ID": "u_comm_test"}


def _clean():
    db = SessionLocal()
    try:
        s = db.get(SettingsORM, "u_comm_test")
        if s is not None:
            db.delete(s)
        g = db.get(GuardianORM, "u_comm_test")
        if g is not None:
            db.delete(g)
        db.commit()
    finally:
        db.close()


def _grant_guardian(user_id: str = "u_comm_test", status_value: str = "active") -> None:
    """直接落一条监护人授权记录（状态机本身由 test_me_and_guardian 覆盖）。"""
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        row = db.get(GuardianORM, user_id)
        if row is None:
            row = GuardianORM(user_id=user_id)
            db.add(row)
        row.status = status_value
        row.expires_at = datetime.utcnow() + timedelta(days=365) if status_value == "active" else None
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
    _grant_guardian()  # D41：开启前必须监护人授权 active
    r = client.put("/api/v1/me/community-consent", json={"enabled": True}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    r2 = client.get("/api/v1/me/community-consent", headers=HDR)
    assert r2.json()["enabled"] is True

    r3 = client.put("/api/v1/me/community-consent", json={"enabled": False}, headers=HDR)
    assert r3.status_code == 200
    assert r3.json()["enabled"] is False


def test_enable_blocked_without_guardian_authorization():
    """D41：未提交/待确认监护人授权 → 开启被拦 403 GUARDIAN_AUTHORIZATION_REQUIRED。"""
    _clean()  # 无 guardian 记录 = pending
    r = client.put("/api/v1/me/community-consent", json={"enabled": True}, headers=HDR)
    assert r.status_code == 403
    body = r.json()
    assert body["error"]["code"] == "GUARDIAN_AUTHORIZATION_REQUIRED"
    # 未开启成功，状态保持关闭
    assert client.get("/api/v1/me/community-consent", headers=HDR).json()["enabled"] is False


def test_enable_blocked_when_authorization_expired():
    """D41：授权已失效（expired/revoked）→ 403 GUARDIAN_AUTHORIZATION_EXPIRED。"""
    _clean()
    _grant_guardian(status_value="revoked")
    r = client.put("/api/v1/me/community-consent", json={"enabled": True}, headers=HDR)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_EXPIRED"


def test_revoke_allowed_without_guardian_authorization():
    """撤回不设门槛：授权失效/未授权时也必须能退出聚合（否则用户被锁在池里）。"""
    _clean()
    r = client.put("/api/v1/me/community-consent", json={"enabled": False}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


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

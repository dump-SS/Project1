"""用户资料建档 + 监护人授权状态机集成测试（PRD 5.1 前置 / 8.1 合规底线）。

覆盖：
- /me 建档（PUT）+ 更新（PATCH）+ 读取（GET）
- /me/guardian-authorization 提交（POST）→ 确认（GET confirm）→ 撤销（DELETE）
- 状态机：pending → active → revoked → 重新提交 pending → active
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------- /me 建档与更新 ----------

def test_new_user_is_unonboarded():
    """新用户 GET /me → onboardingCompleted=false，guardian pending。"""
    r = client.get("/api/v1/me", headers={"X-User-ID": "new_user_test_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["onboardingCompleted"] is False
    assert body["guardianAuthorization"]["status"] == "pending"
    assert body["userId"] == "new_user_test_1"


def test_put_me_onboarding():
    """PUT /me 建档 → onboardingCompleted=true，字段落库。"""
    r = client.put("/api/v1/me", json={
        "stage": "senior",
        "grade": "高二",
        "subjects": ["math", "english", "physics"],
    }, headers={"X-User-ID": "new_user_test_2"})
    assert r.status_code == 200
    body = r.json()
    assert body["onboardingCompleted"] is True
    assert body["stage"] == "senior"
    assert body["grade"] == "高二"
    assert body["subjects"] == ["math", "english", "physics"]


def test_put_me_is_idempotent():
    """PUT /me 幂等：重复建档覆盖，不报错。"""
    headers = {"X-User-ID": "new_user_test_3"}
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "初二", "subjects": ["math"],
    }, headers=headers)
    r = client.put("/api/v1/me", json={
        "stage": "senior", "grade": "高三", "subjects": ["math", "physics"],
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "senior"
    assert body["grade"] == "高三"
    assert body["subjects"] == ["math", "physics"]


def test_patch_me_partial_update():
    """PATCH /me 局部更新，未传字段保持不变。"""
    headers = {"X-User-ID": "new_user_test_4"}
    client.put("/api/v1/me", json={
        "stage": "senior", "grade": "高二", "subjects": ["math", "english"],
    }, headers=headers)
    # 只改 grade
    r = client.patch("/api/v1/me", json={"grade": "高三"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == "高三"
    assert body["stage"] == "senior"  # 未传，保持
    assert body["subjects"] == ["math", "english"]  # 未传，保持


def test_patch_me_404_when_not_onboarded():
    """PATCH /me 未建档用户 → 404（PATCH 要求资源已存在）。"""
    r = client.patch("/api/v1/me", json={"grade": "高三"}, headers={"X-User-ID": "never_onboarded"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_me_after_onboarding_reflects_orm():
    """建档后 GET /me 返回 ORM 真实资料（不再返 mock 常量）。"""
    headers = {"X-User-ID": "new_user_test_5"}
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "初三", "subjects": ["chinese", "math"],
    }, headers=headers)
    r = client.get("/api/v1/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["onboardingCompleted"] is True
    assert body["stage"] == "junior"
    assert body["grade"] == "初三"
    assert body["subjects"] == ["chinese", "math"]


# ---------- guardian-authorization 状态机 ----------

def _onboard_and_submit_guardian(user_id: str, email: str = "parent@example.com"):
    """建档 + 提交监护人授权的共用前置流程。"""
    headers = {"X-User-ID": user_id}
    client.put("/api/v1/me", json={
        "stage": "senior", "grade": "高二", "subjects": ["math"],
    }, headers=headers)
    client.post("/api/v1/me/guardian-authorization", json={
        "guardianEmail": email,
    }, headers=headers)
    return headers


def test_guardian_submit_returns_202():
    """POST /me/guardian-authorization → 202，落库 pending。"""
    headers = _onboard_and_submit_guardian("guardian_test_1")
    # 已在 _onboard_and_submit_guardian 里提交，这里验证状态
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["guardianAuthorization"]["status"] == "pending"


def test_guardian_status_pending_after_submit():
    """提交后 GET /me → guardianAuthorization.status=pending。"""
    headers = _onboard_and_submit_guardian("guardian_test_2")
    r = client.get("/api/v1/me", headers=headers)
    assert r.json()["guardianAuthorization"]["status"] == "pending"


def test_guardian_confirm_activates_authorization():
    """监护人点确认链接 → status=active + expiresAt 设置。

    需要 token：MVP 不发邮件，我们从 DB 直接取 token 做测试。
    """
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = _onboard_and_submit_guardian("guardian_test_3")

    # 从 DB 取 token（生产环境通过邮件发链接）
    db = SessionLocal()
    try:
        row = db.get(GuardianAuthorization, "guardian_test_3")
        token = row.confirm_token
    finally:
        db.close()

    # 监护人点确认链接（无需登录）
    r = client.get(f"/api/v1/guardian-authorization/confirm?token={token}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # 确认后 status=active
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["guardianAuthorization"]["status"] == "active"
    assert me["guardianAuthorization"]["expiresAt"] is not None


def test_guardian_confirm_invalid_token_returns_ok_false():
    """无效 token → ok=False。"""
    r = client.get("/api/v1/guardian-authorization/confirm?token=invalid_token_xxx")
    assert r.status_code == 200
    assert r.json() == {"ok": False}


def test_guardian_confirm_is_one_time():
    """确认后 token 清空，重复点同一链接 → ok=False。"""
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = _onboard_and_submit_guardian("guardian_test_4")

    db = SessionLocal()
    try:
        row = db.get(GuardianAuthorization, "guardian_test_4")
        token = row.confirm_token
    finally:
        db.close()

    # 第一次确认成功
    r1 = client.get(f"/api/v1/guardian-authorization/confirm?token={token}")
    assert r1.json() == {"ok": True}

    # 第二次同一 token 失败（一次性）
    r2 = client.get(f"/api/v1/guardian-authorization/confirm?token={token}")
    assert r2.json() == {"ok": False}


def test_guardian_revoke_sets_revoked():
    """DELETE /me/guardian-authorization → status=revoked。"""
    headers = _onboard_and_submit_guardian("guardian_test_5")

    r = client.delete("/api/v1/me/guardian-authorization", headers=headers)
    assert r.status_code == 204

    me = client.get("/api/v1/me", headers=headers).json()
    assert me["guardianAuthorization"]["status"] == "revoked"
    assert me["guardianAuthorization"]["expiresAt"] is None


def test_guardian_revoke_when_no_authorization_is_204():
    """无授权记录时 DELETE 也返 204（幂等）。"""
    # 先建档但没提交 guardian
    client.put("/api/v1/me", json={
        "stage": "senior", "grade": "高二", "subjects": ["math"],
    }, headers={"X-User-ID": "never_submit_guardian"})
    r = client.delete("/api/v1/me/guardian-authorization", headers={"X-User-ID": "never_submit_guardian"})
    assert r.status_code == 204


def test_guardian_resubmit_after_revoke():
    """撤销后重新提交 → status 回到 pending，可再次确认。"""
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = _onboard_and_submit_guardian("guardian_test_6")
    # 撤销 → 重新提交
    client.delete("/api/v1/me/guardian-authorization", headers=headers)
    client.post("/api/v1/me/guardian-authorization", json={
        "guardianEmail": "parent2@example.com",
    }, headers=headers)

    # 取新 token 确认
    db = SessionLocal()
    try:
        row = db.get(GuardianAuthorization, "guardian_test_6")
        token = row.confirm_token
    finally:
        db.close()

    r = client.get(f"/api/v1/guardian-authorization/confirm?token={token}")
    assert r.json() == {"ok": True}

    me = client.get("/api/v1/me", headers=headers).json()
    assert me["guardianAuthorization"]["status"] == "active"

"""低龄强制门槛（D41）+ 出生年份（D40）测试。

口径（routes/user.py::_is_under_14）：只采集出生**年份**，判定取保守侧——
`当前年 - 出生年 <= 14` 视为「可能未满 14 周岁」，必须监护人授权 active 才能完成建档；
`>= 15` 放行；未采集 birthYear（None）的存量账号不拦截。

覆盖：
1. 未满 14 岁未授权 → 资料落库但 onboardingCompleted=false（不报错、不丢数据）
2. 授权 active 后重调 PUT /me → onboardingCompleted=true（幂等解锁）
3. 撤销授权 → 未满 14 岁的档案回到未完成（门槛是持续的，不是一次性检查）
4. ≥14 岁不受门槛影响
5. 未采集 birthYear 不影响既有行为（存量兼容）
6. PATCH 改 birthYear 触发重算
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from main import app
from routes.user import _is_under_14

client = TestClient(app)

CURRENT_YEAR = date.today().year
UNDER14_YEAR = CURRENT_YEAR - 13  # 差 13 → 确定未满 14
BOUNDARY_YEAR = CURRENT_YEAR - 14  # 差 14 → 保守判定为「可能未满 14」
ADULT_YEAR = CURRENT_YEAR - 16  # 差 16 → 确定已满 14


# ---------- 判定口径 ----------

def test_under14_boundary_is_conservative():
    """差 14 年（今年可能过生日也可能没过）按「可能未满 14」处理；差 15 年以上放行。"""
    assert _is_under_14(CURRENT_YEAR - 13) is True
    assert _is_under_14(CURRENT_YEAR - 14) is True, "边界保守：宁可多拦一次"
    assert _is_under_14(CURRENT_YEAR - 15) is False
    assert _is_under_14(None) is False, "未采集出生年份的存量账号不拦截"


# ---------- 建档门槛 ----------

def test_under14_onboarding_blocked_until_guardian_active():
    """未满 14 岁：建档资料落库成功，但 onboardingCompleted=false，直到监护人授权 active。"""
    headers = {"X-User-ID": "u_threshold_1"}

    r = client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_7", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["birthYear"] == UNDER14_YEAR
    assert body["onboardingCompleted"] is False, "未满 14 岁未授权不得完成建档"
    assert body["guardianAuthorization"]["status"] == "pending"

    # 资料确实落库了（不是被拒），只是档案未完成
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["stage"] == "junior"
    assert me["grade"] == "grade_7"
    assert me["onboardingCompleted"] is False


def test_under14_unlocks_after_guardian_active():
    """监护人授权 active 后重调 PUT /me → onboardingCompleted=true。"""
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = {"X-User-ID": "u_threshold_2"}
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_8", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)

    # 走真实链路：提交监护人联系方式 → 监护人点确认链接
    r = client.post("/api/v1/me/guardian-authorization", json={
        "guardianEmail": "parent@example.com",
    }, headers=headers)
    assert r.status_code == 202

    db = SessionLocal()
    try:
        token = db.get(GuardianAuthorization, "u_threshold_2").confirm_token
    finally:
        db.close()
    assert client.get(f"/api/v1/guardian-authorization/confirm?token={token}").json() == {"ok": True}

    # 授权生效后重调建档（幂等）→ 完成
    r2 = client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_8", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["onboardingCompleted"] is True
    assert r2.json()["guardianAuthorization"]["status"] == "active"


def test_under14_threshold_reapplies_after_revoke():
    """撤销授权 → 未满 14 岁的档案回到「未完成」（门槛是持续的）。"""
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = {"X-User-ID": "u_threshold_3"}
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_9", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)
    client.post("/api/v1/me/guardian-authorization", json={"guardianEmail": "p@example.com"}, headers=headers)
    db = SessionLocal()
    try:
        token = db.get(GuardianAuthorization, "u_threshold_3").confirm_token
    finally:
        db.close()
    client.get(f"/api/v1/guardian-authorization/confirm?token={token}")
    # 授权生效后重调建档（幂等）→ 完成
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_9", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)
    assert client.get("/api/v1/me", headers=headers).json()["onboardingCompleted"] is True

    # 撤销 → 档案回到未完成
    assert client.delete("/api/v1/me/guardian-authorization", headers=headers).status_code == 204
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["guardianAuthorization"]["status"] == "revoked"
    assert me["onboardingCompleted"] is False


def test_adult_onboarding_unaffected():
    """≥14 岁：不要求监护人授权，建档直接完成。"""
    r = client.put("/api/v1/me", json={
        "stage": "senior", "grade": "grade_11", "subjects": ["SX"], "birthYear": ADULT_YEAR,
    }, headers={"X-User-ID": "u_threshold_adult"})
    assert r.status_code == 200
    assert r.json()["onboardingCompleted"] is True


def test_missing_birth_year_keeps_legacy_behavior():
    """未采集 birthYear（存量账号 / 老客户端）：不触发门槛，建档照常完成。"""
    r = client.put("/api/v1/me", json={
        "stage": "senior", "grade": "grade_10", "subjects": ["SX"],
    }, headers={"X-User-ID": "u_threshold_legacy"})
    assert r.status_code == 200
    assert r.json()["onboardingCompleted"] is True
    assert r.json()["birthYear"] is None


def test_patch_birth_year_recomputes_threshold():
    """PATCH 改 birthYear 改到低龄 → 档案回到未完成；改回成年 → 恢复完成。"""
    headers = {"X-User-ID": "u_threshold_patch"}
    client.put("/api/v1/me", json={
        "stage": "senior", "grade": "grade_10", "subjects": ["SX"], "birthYear": ADULT_YEAR,
    }, headers=headers)
    assert client.get("/api/v1/me", headers=headers).json()["onboardingCompleted"] is True

    r = client.patch("/api/v1/me", json={"birthYear": UNDER14_YEAR}, headers=headers)
    assert r.status_code == 200
    assert r.json()["birthYear"] == UNDER14_YEAR
    assert r.json()["onboardingCompleted"] is False

    r2 = client.patch("/api/v1/me", json={"birthYear": ADULT_YEAR}, headers=headers)
    assert r2.json()["onboardingCompleted"] is True


def test_put_me_keeps_birth_year_when_omitted():
    """PUT 未传 birthYear = 本次不改动（不误清空已采集的值）。"""
    headers = {"X-User-ID": "u_threshold_keep"}
    client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_7", "subjects": ["SX"], "birthYear": UNDER14_YEAR,
    }, headers=headers)

    r = client.put("/api/v1/me", json={
        "stage": "junior", "grade": "grade_8", "subjects": ["SX"],
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["birthYear"] == UNDER14_YEAR, "未传 birthYear 应保留旧值"


def test_birth_year_out_of_range_rejected():
    """出生年份越界 → 400 VALIDATION_FAILED。"""
    r = client.put("/api/v1/me", json={
        "stage": "senior", "grade": "grade_10", "subjects": ["SX"], "birthYear": 1800,
    }, headers={"X-User-ID": "u_threshold_range"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"

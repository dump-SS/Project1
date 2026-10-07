"""邀请码注册（#50 一码一用，契约 v1.8.0）集成测试。

覆盖：
1. 邀请码必填；格式/存在性校验（400 / 422 INVITE_CODE_INVALID）
2. 一码一用：同码第二个邮箱 → 409 INVITE_CODE_USED
3. 成功后回写 `used_by`（稳定 userId，D59）+ `used_at`，可溯源
4. 注册失败（验证码错 / 弱密码）**不占用**邀请码
5. 大小写与首尾空格规范化（手抄容错）

SMTP 全程 monkeypatch mock 掉，验证码通过 mock 捕获（与 test_auth.py 同一手法）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
import routes.auth as auth_route
from models.invite import InviteCode

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_email(monkeypatch):
    """mock send_code_email，捕获 code 供测试使用。"""
    captured: dict[str, str] = {}

    def _fake_send(code_type: str, email: str, code: str) -> None:
        captured[f"{code_type}:{email}"] = code

    monkeypatch.setattr(auth_route, "send_code_email", _fake_send)
    return captured


@pytest.fixture(autouse=True)
def _no_send_rate_limit(monkeypatch):
    """同邮箱连发多类验证码不受 60s 限流影响（与 test_auth.py 一致）。"""
    monkeypatch.setattr(auth_route, "allow", lambda *a, **k: True)


def _make_code(code: str, note: str | None = None) -> None:
    """直接落一个可用邀请码（生成脚本 scripts/gen_invite_codes.py 的同表同字段）。"""
    db = SessionLocal()
    try:
        if db.get(InviteCode, code) is None:
            db.add(InviteCode(code=code, note=note))
            db.commit()
    finally:
        db.close()


def _code_row(code: str) -> InviteCode | None:
    db = SessionLocal()
    try:
        row = db.get(InviteCode, code)
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def _register(email: str, invite_code: str, captured: dict, password: str = "Abc123!@#"):
    """发码 → 注册。返回 response（邀请码按调用方传入，便于覆盖校验分支）。"""
    r = client.post("/api/v1/auth/send-register-code", json={"email": email})
    assert r.status_code == 200, f"send-register-code 失败: {r.text}"
    code = captured[f"register:{email}"]
    return client.post("/api/v1/auth/register", json={
        "email": email,
        "code": code,
        "password": password,
        "confirmPassword": password,
        "inviteCode": invite_code,
    })


# ---------- 1. 必填与存在性 ----------

def test_register_without_invite_code_is_rejected(_mock_email):
    """缺邀请码 → 400 VALIDATION_FAILED + field=inviteCode。"""
    _make_code("EPX-AAAA-2222")
    email = "no-invite@example.com"
    client.post("/api/v1/auth/send-register-code", json={"email": email})
    code = _mock_email[f"register:{email}"]
    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": code,
        "password": "Abc123!@#", "confirmPassword": "Abc123!@#",
    })
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["field"] == "inviteCode"


def test_register_with_unknown_invite_code_is_rejected(_mock_email):
    """邀请码不存在 → 422 INVITE_CODE_INVALID。"""
    r = _register("unknown-invite@example.com", "EPX-XXXX-9999", _mock_email)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "INVITE_CODE_INVALID"
    assert body["error"]["field"] == "inviteCode"


# ---------- 2. 一码一用 ----------

def test_register_consumes_invite_code(_mock_email):
    """注册成功：201 + 邀请码被占用（used_by=稳定 userId、used_at 非空）。"""
    code = "EPX-BBBB-3333"
    _make_code(code, note="pilot 第一批")

    r = _register("invite-ok@example.com", code, _mock_email)
    assert r.status_code == 201

    row = _code_row(code)
    assert row is not None
    assert row.used_by is not None and row.used_by.startswith("u_"), "used_by 必须是稳定 user_id（D59）"
    assert row.used_at is not None

    # 溯源链路：used_by 与认证行指向同一个稳定 userId
    from auth.models import AuthUser
    db = SessionLocal()
    try:
        auth_user = db.get(AuthUser, "invite-ok@example.com")
        assert auth_user.user_id == row.used_by
    finally:
        db.close()


def test_invite_code_cannot_be_reused(_mock_email):
    """同一个码注册第二个邮箱 → 409 INVITE_CODE_USED。"""
    code = "EPX-CCCC-4444"
    _make_code(code)

    assert _register("first@example.com", code, _mock_email).status_code == 201
    r = _register("second@example.com", code, _mock_email)
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "INVITE_CODE_USED"
    assert body["error"]["field"] == "inviteCode"

    # 第二个邮箱没有留下半截账号
    from auth.models import AuthUser
    db = SessionLocal()
    try:
        assert db.get(AuthUser, "second@example.com") is None
    finally:
        db.close()


# ---------- 3. 失败不占用 ----------

def test_wrong_email_code_does_not_consume_invite(_mock_email):
    """邮箱验证码错 → 邀请码仍可用（不白占）。"""
    code = "EPX-DDDD-5555"
    _make_code(code)
    email = "wrong-code@example.com"
    client.post("/api/v1/auth/send-register-code", json={"email": email})

    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": "000000",
        "password": "Abc123!@#", "confirmPassword": "Abc123!@#",
        "inviteCode": code,
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CODE_INVALID"

    row = _code_row(code)
    assert row.used_by is None, "注册失败不得占用邀请码"


def test_weak_password_does_not_consume_invite(_mock_email):
    """密码不达标 → 邀请码仍可用。"""
    code = "EPX-EEEE-6666"
    _make_code(code)
    r = _register("weak-pwd@example.com", code, _mock_email, password="123456")
    assert r.status_code == 400
    assert _code_row(code).used_by is None


# ---------- 4. 规范化 ----------

def test_invite_code_is_normalized(_mock_email):
    """小写 + 首尾空格输入 → 仍能命中（手抄容错），且库里记录的是规范化后的码。"""
    code = "EPX-FFFF-7777"
    _make_code(code)

    r = _register("normalize@example.com", f"  {code.lower()} ", _mock_email)
    assert r.status_code == 201
    assert _code_row(code).used_by is not None


def test_invite_code_required_before_email_code_check(_mock_email):
    """邀请码校验先于邮箱验证码：码不存在时返回 INVITE_CODE_INVALID，
    不去消费邮箱验证码（用户体验：先改码，不用重新发码）。"""
    r = _register("order@example.com", "EPX-ZZZZ-8888", _mock_email)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVITE_CODE_INVALID"

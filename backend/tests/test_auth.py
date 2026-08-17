"""Auth 迁移后端到端测试：注册 / 登录 / 会话 / 重置密码全链路。

覆盖目标（与 mock-server 行为对齐）：
1. 注册：send-register-code → register（含密码强度/确认/重复邮箱校验）
2. 密码登录：错误密码 401、正确密码 200 + Set-Cookie
3. 验证码登录：send-login-code → login-email-code
4. /me：带 cookie 返回 email；无 cookie 401
5. /logout：销毁会话后再 /me 401
6. 重置密码：send-reset-code → verify-reset-code → reset-password → 旧 session 失效
7. 限流：连续 5 次错误密码 → 锁定 15 分钟

SMTP 全程 monkeypatch mock 掉，验证码通过 mock 捕获（不真发邮件）。
限流是进程内存级，每个用例前清空桶，避免跨用例污染。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from main import app
import routes.auth as auth_route
from auth import rate_limit

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_email(monkeypatch):
    """mock send_code_email，捕获 code 供测试使用。"""
    captured: dict[str, str] = {}

    def _fake_send(code_type: str, email: str, code: str) -> None:
        captured[f"{code_type}:{email}"] = code

    # routes/auth.py 顶部 `from auth.email import send_code_email`，
    # 所以要 patch 它在 routes.auth 命名空间里的引用
    monkeypatch.setattr(auth_route, "send_code_email", _fake_send)
    return captured


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """默认关闭「验证码发送」限流。

    routes/auth.py 的 allow(key, ...) key 形如 `code:<email>`，不区分类型——
    同邮箱 60s 内连发 register + login/reset 码会被限流误伤。
    把 allow 临时放行，让正常流程测试用例能连发不同类型的码。

    `test_send_code_rate_limit` 单独还原真实 allow，验证限流逻辑。
    锁定逻辑（is_locked/record_fail/clear_fails）不受影响，仍走真实实现。
    """
    monkeypatch.setattr(auth_route, "allow", lambda *a, **k: True)

    # 清掉上一用例残留的失败计数，避免锁定状态污染
    rate_limit._login_fails.clear()
    yield
    rate_limit._login_fails.clear()


# ---------- 辅助 ----------

def _register(client: TestClient, email: str, password: str, captured: dict) -> int:
    """跑完整注册流程：发码 → 用捕获到的 code 注册。返回 status_code。"""
    r = client.post("/api/v1/auth/send-register-code", json={"email": email})
    assert r.status_code == 200, f"send-register-code 失败: {r.text}"
    code = captured[f"register:{email}"]
    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": code,
        "password": password, "confirmPassword": password,
    })
    return r.status_code


# ---------- 1. 注册 ----------

def test_register_happy_path(_mock_email):
    """注册成功：send-register-code → register 201。"""
    email = "alice@example.com"
    captured = _mock_email
    assert _register(client, email, "Abc123!@#", captured) == 201


def test_register_invalid_email(_mock_email):
    """邮箱格式错 → 400 VALIDATION_FAILED + field=email。"""
    r = client.post("/api/v1/auth/send-register-code", json={"email": "not-an-email"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["field"] == "email"


def test_register_duplicate_email(_mock_email):
    """重复邮箱注册 → 409 EMAIL_ALREADY_REGISTERED。"""
    captured = _mock_email
    _register(client, "dup@example.com", "Abc123!@#", captured)
    r = client.post("/api/v1/auth/send-register-code", json={"email": "dup@example.com"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_register_weak_password(_mock_email):
    """弱密码（仅数字）→ 400。"""
    captured = _mock_email
    email = "weak@example.com"
    client.post("/api/v1/auth/send-register-code", json={"email": email})
    code = captured[f"register:{email}"]
    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": code,
        "password": "123456", "confirmPassword": "123456",
    })
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "password"


def test_register_password_mismatch(_mock_email):
    """两次密码不一致 → 400 + field=confirmPassword。"""
    captured = _mock_email
    email = "mismatch@example.com"
    client.post("/api/v1/auth/send-register-code", json={"email": email})
    code = captured[f"register:{email}"]
    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": code,
        "password": "Abc123!@#", "confirmPassword": "Abc123!@X",
    })
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "confirmPassword"


def test_register_wrong_code(_mock_email):
    """验证码错 → 400 CODE_INVALID。"""
    captured = _mock_email
    email = "wrongcode@example.com"
    client.post("/api/v1/auth/send-register-code", json={"email": email})
    r = client.post("/api/v1/auth/register", json={
        "email": email, "code": "000000",
        "password": "Abc123!@#", "confirmPassword": "Abc123!@#",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CODE_INVALID"


# ---------- 2. 密码登录 ----------

def test_login_password_happy_path(_mock_email):
    """密码登录成功 → 200 + Set-Cookie。"""
    captured = _mock_email
    email = "login@example.com"
    _register(client, email, "Abc123!@#", captured)
    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "Abc123!@#",
    })
    assert r.status_code == 200, r.text
    assert "set-cookie" in {k.lower() for k in r.headers}
    assert "sid=" in r.headers["set-cookie"]


def test_login_password_unregistered(_mock_email):
    """未注册邮箱登录 → 404 EMAIL_NOT_REGISTERED。"""
    r = client.post("/api/v1/auth/login-password", json={
        "email": "ghost@example.com", "password": "Abc123!@#",
    })
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "EMAIL_NOT_REGISTERED"


def test_login_password_wrong(_mock_email):
    """密码错 → 401 PASSWORD_INCORRECT。"""
    captured = _mock_email
    email = "wrongpw@example.com"
    _register(client, email, "Abc123!@#", captured)
    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "Wrong123!@",
    })
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "PASSWORD_INCORRECT"


def test_login_password_lockout_after_5_fails(_mock_email):
    """连续 5 次错误密码 → 第 6 次 429 RATE_LIMITED。"""
    captured = _mock_email
    email = "lockout@example.com"
    _register(client, email, "Abc123!@#", captured)
    for _ in range(5):
        client.post("/api/v1/auth/login-password", json={
            "email": email, "password": "Wrong123!@",
        })
    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "Wrong123!@",
    })
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


# ---------- 3. 验证码登录 ----------

def test_login_email_code_happy_path(_mock_email):
    """验证码登录成功 → 200 + Set-Cookie。"""
    captured = _mock_email
    email = "code-login@example.com"
    _register(client, email, "Abc123!@#", captured)

    r = client.post("/api/v1/auth/send-login-code", json={"email": email})
    assert r.status_code == 200
    code = captured[f"login:{email}"]

    r = client.post("/api/v1/auth/login-email-code", json={
        "email": email, "code": code,
    })
    assert r.status_code == 200, r.text
    assert "sid=" in r.headers["set-cookie"]


def test_login_email_code_unregistered(_mock_email):
    """未注册邮箱发登录码 → 404。"""
    r = client.post("/api/v1/auth/send-login-code", json={"email": "nobody@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "EMAIL_NOT_REGISTERED"


def test_login_email_code_wrong(_mock_email):
    """验证码错 → 400 CODE_INVALID。"""
    captured = _mock_email
    email = "wronglogincode@example.com"
    _register(client, email, "Abc123!@#", captured)
    client.post("/api/v1/auth/send-login-code", json={"email": email})
    r = client.post("/api/v1/auth/login-email-code", json={
        "email": email, "code": "000000",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CODE_INVALID"


# ---------- 4. /me ----------

def test_me_with_session(_mock_email):
    """登录后带 cookie 调 /me → 200 + email。"""
    captured = _mock_email
    email = "me@example.com"
    _register(client, email, "Abc123!@#", captured)

    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "Abc123!@#",
    })
    # TestClient 会自动管理 cookie jar
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == email


def test_me_without_session(_mock_email):
    """无 cookie 调 /me → 401。"""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


# ---------- 5. /logout ----------

def test_logout_destroys_session(_mock_email):
    """logout 后再调 /me → 401。"""
    captured = _mock_email
    email = "logout@example.com"
    _register(client, email, "Abc123!@#", captured)
    client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "Abc123!@#",
    })

    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200

    # logout 后 cookie 会被清，但 TestClient 仍带着旧 sid；
    # 服务端已删除会话行，所以 /me 应 401
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


# ---------- 6. 重置密码 ----------

def test_reset_password_full_flow(_mock_email):
    """完整重置流程：发码 → 校验 → 重置 → 旧密码失败、新密码成功。"""
    captured = _mock_email
    email = "reset@example.com"
    _register(client, email, "OldPass!@#", captured)

    # 先建立旧 session（重置后应该失效）
    client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "OldPass!@#",
    })
    assert client.get("/api/v1/auth/me").status_code == 200

    # 发重置码
    r = client.post("/api/v1/auth/send-reset-code", json={"email": email})
    assert r.status_code == 200
    code = captured[f"reset:{email}"]

    # 校验码（不消费）
    r = client.post("/api/v1/auth/verify-reset-code", json={
        "email": email, "code": code,
    })
    assert r.status_code == 200

    # 重置密码
    r = client.post("/api/v1/auth/reset-password", json={
        "email": email, "code": code,
        "newPassword": "NewPass!@#", "confirmPassword": "NewPass!@#",
    })
    assert r.status_code == 200, r.text

    # 旧 session 应已失效
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401, "重置密码后旧 session 应失效"

    # 旧密码登录失败
    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "OldPass!@#",
    })
    assert r.status_code == 401

    # 新密码登录成功
    r = client.post("/api/v1/auth/login-password", json={
        "email": email, "password": "NewPass!@#",
    })
    assert r.status_code == 200


def test_reset_password_unregistered(_mock_email):
    """未注册邮箱发重置码 → 404。"""
    r = client.post("/api/v1/auth/send-reset-code", json={"email": "ghost@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "EMAIL_NOT_REGISTERED"


def test_reset_password_mismatch(_mock_email):
    """重置时两次密码不一致 → 400 + field=confirmPassword。"""
    captured = _mock_email
    email = "reset-mismatch@example.com"
    _register(client, email, "OldPass!@#", captured)
    client.post("/api/v1/auth/send-reset-code", json={"email": email})
    code = captured[f"reset:{email}"]
    r = client.post("/api/v1/auth/reset-password", json={
        "email": email, "code": code,
        "newPassword": "NewPass!@#", "confirmPassword": "NewPass!@X",
    })
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "confirmPassword"


# ---------- 7. 验证码限流 ----------

def test_send_code_rate_limit(_mock_email, monkeypatch):
    """同邮箱 60 秒内连发 2 次验证码 → 第 2 次 429。

    autouse 的 _no_rate_limit 默认放行了 allow，这里手动还原真实实现。
    """
    monkeypatch.setattr(auth_route, "allow", rate_limit.allow)
    rate_limit._rate_buckets.clear()

    email = "rate@example.com"
    r1 = client.post("/api/v1/auth/send-register-code", json={"email": email})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/auth/send-register-code", json={"email": email})
    assert r2.status_code == 429
    assert r2.json()["error"]["code"] == "RATE_LIMITED"

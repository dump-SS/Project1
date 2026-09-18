"""部署形态配置测试：CORS 白名单 + Cookie Secure/SameSite。

对应部署评估文档 §2-5 / §2-6：
- §2-5 `allow_origins=["*"]` + `allow_credentials=True` 是浏览器规范禁止的组合，
  之前不报错只是因为 Vite dev 代理成了同源、CORS 从未被触发
- §2-6 cookie 缺 Secure；跨站部署还需 SameSite=None

首选形态是同域部署（域/app + 域/api），此时 CORS 不需要、SameSite=Lax 够用；
分域部署才走配置。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from auth import session
from auth.session import create_session
from config import settings
from database import SessionLocal
from main import app

client = TestClient(app)


# ---------- Cookie 属性 ----------

def test_cookie_attrs_default_is_lax_without_secure(monkeypatch):
    """默认（同域部署）：HttpOnly + SameSite=Lax，且不加 Secure。

    本地开发走 http，加了 Secure 浏览器就不回传 cookie，登录态会直接失效——
    所以默认必须是 false。
    """
    monkeypatch.setattr(settings, "cookie_samesite", "lax")
    monkeypatch.setattr(settings, "cookie_secure", False)

    attrs = session._cookie_attrs()
    assert "HttpOnly" in attrs
    assert "SameSite=Lax" in attrs
    assert "Secure" not in attrs


def test_cookie_attrs_adds_secure_when_configured(monkeypatch):
    """HTTPS 生产：COOKIE_SECURE=true 时补上 Secure。"""
    monkeypatch.setattr(settings, "cookie_secure", True)

    assert "Secure" in session._cookie_attrs()


def test_cookie_attrs_forces_secure_for_samesite_none(monkeypatch):
    """分域部署：SameSite=None 时自动补 Secure。

    浏览器对 SameSite=None 强制要求 Secure，漏掉的话 cookie 会被直接丢弃，
    表现为「登录接口 200 但下一个请求又是未登录」，很难排查。
    """
    monkeypatch.setattr(settings, "cookie_samesite", "none")
    monkeypatch.setattr(settings, "cookie_secure", False)

    attrs = session._cookie_attrs()
    assert "SameSite=None" in attrs
    assert "Secure" in attrs


def test_create_session_cookie_uses_configured_attrs(monkeypatch):
    """create_session 返回的 cookie 串走同一套属性（不是另写一份）。"""
    monkeypatch.setattr(settings, "cookie_secure", True)

    db = SessionLocal()
    try:
        # 参数是稳定 user_id（D59 后会话存 user_id 不存 email）；本用例只验 cookie 属性
        _sid, cookie = create_session(db, "u_cookie_attrs_test")
    finally:
        db.close()

    assert cookie.startswith("sid=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "Max-Age=" in cookie


def test_destroy_session_clears_with_same_attrs(monkeypatch):
    """清空 cookie 与下发 cookie 用同一套属性，避免残留一个 Secure 不一致的版本。"""
    monkeypatch.setattr(settings, "cookie_secure", True)

    db = SessionLocal()
    try:
        sid, _ = create_session(db, "u_cookie_clear_test")
        cleared = session.destroy_session(db, sid)
    finally:
        db.close()

    assert cleared.startswith("sid=;")
    assert "Secure" in cleared
    assert "Max-Age=0" in cleared


# ---------- CORS ----------

def test_cors_origins_empty_by_default():
    """默认不配白名单——同域部署本就不需要 CORS。"""
    assert settings.cors_allow_origins == ""


def test_no_cors_header_by_default():
    """默认形态下响应不带 CORS 头（没有中间件，也就没有通配来源）。

    等价于断言「不再使用 allow_origins=["*"]」：带凭据的通配来源是浏览器规范禁止的。
    """
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_preflight_not_wildcard():
    """带 Origin 的预检请求不应拿到通配的 allow-origin（那会与凭据冲突）。"""
    r = client.options(
        "/api/v1/me",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") != "*"

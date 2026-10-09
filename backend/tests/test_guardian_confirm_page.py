"""监护人确认结果页测试（#D41 收尾）。

背景：`GET /guardian-authorization/confirm` 此前只返回裸 JSON `{"ok": true}`，
监护人（不装 App、不登录、从邮件里点开链接）看到的就是一行 JSON——本模块验证
`Accept: text/html` 分支返回自包含结果页，同时 JSON 客户端语义不变。

覆盖：
1. 浏览器直开（Accept: text/html）→ HTML 结果页（成功态 / 无效态），自包含（无 JS、无外链）
2. 接口客户端（TestClient 默认 `*/*`、前端 fetch 的 application/json）→ 仍是 {"ok": bool}
3. 结果页不泄敏：不含 token 原文、不含监护人联系方式
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
JSON_ACCEPT = "application/json"


def _pending_token(user_id: str) -> str:
    """建一条 pending 授权并取回 token（MVP 不发邮件，从 DB 取）。"""
    from database import SessionLocal
    from models.user import GuardianAuthorization

    headers = {"X-User-ID": user_id}
    client.post("/api/v1/me/guardian-authorization", json={
        "guardianEmail": "guardian@example.com",
    }, headers=headers)

    db = SessionLocal()
    try:
        return db.get(GuardianAuthorization, user_id).confirm_token
    finally:
        db.close()


def test_browser_confirm_success_returns_html_page():
    """浏览器直开成功链接 → HTML 结果页（成功态）。"""
    token = _pending_token("u_confirm_page_1")

    r = client.get(
        f"/api/v1/guardian-authorization/confirm?token={token}",
        headers={"accept": BROWSER_ACCEPT},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "授权已确认" in html
    assert "监护人授权" in html
    # 自包含：无脚本、无外部资源（监护人不装 App、邮件客户端可能屏蔽外链）
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    # 不泄敏：不回显 token 与监护人联系方式
    assert token not in html
    assert "guardian@example.com" not in html


def test_browser_confirm_invalid_token_returns_html_page():
    """浏览器直开无效/已用链接 → HTML 结果页（无效态），不是裸 JSON。"""
    r = client.get(
        "/api/v1/guardian-authorization/confirm?token=not-a-real-token",
        headers={"accept": BROWSER_ACCEPT},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "链接无效或已使用" in r.text


def test_browser_confirm_second_visit_shows_used_state():
    """同一链接第二次打开（token 已消费）→ 无效态页面。"""
    token = _pending_token("u_confirm_page_2")

    first = client.get(
        f"/api/v1/guardian-authorization/confirm?token={token}",
        headers={"accept": BROWSER_ACCEPT},
    )
    assert "授权已确认" in first.text

    second = client.get(
        f"/api/v1/guardian-authorization/confirm?token={token}",
        headers={"accept": BROWSER_ACCEPT},
    )
    assert "链接无效或已使用" in second.text


def test_json_client_still_gets_ok_payload():
    """前端 fetch / 自动化客户端（Accept 非 text/html）→ 语义不变，仍是 {"ok": bool}。"""
    token = _pending_token("u_confirm_page_3")

    r = client.get(
        f"/api/v1/guardian-authorization/confirm?token={token}",
        headers={"accept": JSON_ACCEPT},
    )
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"ok": True}

    r2 = client.get(
        "/api/v1/guardian-authorization/confirm?token=whatever",
        headers={"accept": JSON_ACCEPT},
    )
    assert r2.json() == {"ok": False}

"""HTTP 5xx 计数回归测试（G 板块 · pilot 一期前置，pilot-metrics-and-admission.md §2.2 / §5 第 1 项）。

守住 7 条口径 + 2 条防漂移：

1. 5xx 被记（两条路径：未处理异常 → 500；显式返回 5xx 响应）
2. 4xx 不记
3. `/health` 不记（探活被刷会稀释分母）
4. 静态资源不记
5. 匿名请求 `user_id = "system"` 且 `userScoped = false`（方案 A）
6. payload 不含 query string / header 等敏感字段（且键集被钉死）
7. 埋点写入失败时主流程照常返回（治理不得阻断业务）

防漂移：
8. 中间件的身份归属与 `current_user` 同源（都走 `routes.deps.resolve_user_id`）
9. `category` 必须是契约枚举内的值（写错会被 `track_event` **静默丢弃**）

做法说明：探针路由**插在路由表最前面**——`main.py` 末尾有一条 SPA catch-all
（`/{full_path:path}`），追加到末尾的路由永远匹配不到。用完即摘，不污染 app。
"""
from __future__ import annotations

import json

import pytest
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import select

from config import settings
from database import SessionLocal
from governance_service import ANALYTICS_CATEGORIES
from http_error_tracking import (
    EVENT_TYPE_HTTP_5XX,
    SYSTEM_USER_ID,
    HttpErrorTrackingMiddleware,
    should_track_path,
)
from main import app
from models.analytics import AnalyticsEvent

client = TestClient(app)
# 未处理异常路径必须用 raise_server_exceptions=False 才能观察到 500 响应
client_no_raise = TestClient(app, raise_server_exceptions=False)

_BOOM = "/api/v1/__test_5xx_boom"          # 抛未处理异常 → 500
_BOOM_RESP = "/api/v1/__test_5xx_response"  # 显式返回 503
_HEALTH_BOOM = "/health"                   # 让探活也 500，验证它确实不被记
_STATIC_BOOM = "/assets/__test_5xx_boom.js"  # 让静态路径也 500，验证它确实不被记


@pytest.fixture()
def probe_routes():
    """临时把探针路由插到路由表最前，测试结束摘掉。"""
    r = APIRouter()

    @r.get(_BOOM)
    def _boom():
        raise RuntimeError("probe: 未处理异常 → 500")

    @r.get(_BOOM_RESP)
    def _boom_response():
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "probe"}},
        )

    @r.get(_HEALTH_BOOM)
    def _health_boom():
        raise RuntimeError("probe: 探活异常")

    @r.get(_STATIC_BOOM)
    def _static_boom():
        raise RuntimeError("probe: 静态资源异常")

    added = list(r.routes)
    app.router.routes[:0] = added
    try:
        yield
    finally:
        for route in added:
            app.router.routes.remove(route)


def _events():
    """读回本用例产生的 http_5xx 埋点（conftest 的 _reset_db 每用例前清表）。"""
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.event_type == EVENT_TYPE_HTTP_5XX
                )
            )
            .scalars()
            .all()
        )
        return [
            (
                row.user_id,
                row.category,
                json.loads(row.payload_json) if row.payload_json else None,
            )
            for row in rows
        ]
    finally:
        db.close()


# ---------- 1. 5xx 被记（两条路径） ----------

def test_unhandled_exception_recorded_as_5xx(probe_routes):
    r = client_no_raise.get(_BOOM, headers={"X-User-ID": "u_probe_5xx"})
    assert r.status_code == 500

    rows = _events()
    assert len(rows) == 1
    user_id, category, payload = rows[0]
    assert user_id == "u_probe_5xx"           # 登录态 → 真实 user_id（方案 A）
    assert category == "ai_quality"           # 契约枚举内的值，否则会被静默丢弃
    assert payload["statusCode"] == 500
    assert payload["path"] == _BOOM
    assert payload["method"] == "GET"
    assert payload["userScoped"] is True
    assert isinstance(payload["durationMs"], (int, float))


def test_explicit_5xx_response_recorded(probe_routes):
    r = client_no_raise.get(_BOOM_RESP, headers={"X-User-ID": "u_probe_503"})
    assert r.status_code == 503

    rows = _events()
    assert len(rows) == 1
    assert rows[0][2]["statusCode"] == 503


# ---------- 2. 4xx 不记 ----------

def test_4xx_not_recorded(probe_routes):
    # category 非法 → 契约校验失败（main.py 的 validation handler 统一返回 4xx）
    r = client.post("/api/v1/analytics/events", json={"category": "not_a_category"})
    assert 400 <= r.status_code < 500

    assert _events() == []


# ---------- 3. /health 不记 ----------

def test_health_5xx_not_recorded(probe_routes):
    r = client_no_raise.get(_HEALTH_BOOM)
    assert r.status_code == 500  # 探针确实炸了，但这条不该进埋点

    assert _events() == []


# ---------- 4. 静态资源不记 ----------

def test_static_asset_5xx_not_recorded(probe_routes):
    r = client_no_raise.get(_STATIC_BOOM)
    assert r.status_code == 500

    assert _events() == []


# ---------- 5. 匿名 → "system" + userScoped=false ----------

def test_anonymous_5xx_uses_system_actor(probe_routes, monkeypatch):
    # 关掉测试环境的身份回落链，模拟生产口径的「无登录态」
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    r = client_no_raise.get(_BOOM)
    assert r.status_code == 500

    rows = _events()
    assert len(rows) == 1
    user_id, _category, payload = rows[0]
    assert user_id == SYSTEM_USER_ID == "system"
    assert payload["userScoped"] is False


# ---------- 6. payload 不含敏感字段 ----------

def test_payload_excludes_query_string_and_headers(probe_routes):
    r = client_no_raise.get(
        _BOOM + "?access_token=SECRET_QUERY_TOKEN",
        headers={
            "Authorization": "Bearer SECRET_HEADER_TOKEN",
            "X-User-ID": "u_probe_secret",
            "X-Custom-Trace": "SECRET_HEADER_VALUE",
        },
    )
    assert r.status_code == 500

    rows = _events()
    assert len(rows) == 1
    payload = rows[0][2]

    # 键集钉死：多一个键（比如 query / headers）这条断言就会红
    assert set(payload) == {"path", "method", "statusCode", "durationMs", "userScoped"}
    assert payload["path"] == _BOOM  # 只有 path，不带 query string

    raw = json.dumps(rows, ensure_ascii=False)
    for secret in ("SECRET_QUERY_TOKEN", "SECRET_HEADER_TOKEN", "SECRET_HEADER_VALUE"):
        assert secret not in raw


# ---------- 7. 埋点失败不阻断业务 ----------

def test_tracking_failure_does_not_break_response(probe_routes, monkeypatch):
    import http_error_tracking

    def _explode(*_args, **_kwargs):
        raise RuntimeError("埋点写入炸了")

    monkeypatch.setattr(http_error_tracking, "track_event", _explode)

    # 显式 5xx 响应：仍返回业务自己的 503，不被中间件改写成 500
    r = client.get(_BOOM_RESP)
    assert r.status_code == 503

    # 未处理异常：仍是 500（业务异常原样抛出），且不是被中间件替换的
    r = client_no_raise.get(_BOOM)
    assert r.status_code == 500


# ---------- 8. 身份归属防漂移 ----------

def test_actor_resolution_matches_current_user(probe_routes):
    """中间件与 current_user 必须对同一请求给出同一个 user_id（同源 resolve_user_id）。"""
    r = client.get("/api/v1/me", headers={"X-User-ID": "u_probe_drift"})
    assert r.status_code == 200
    assert r.json()["userId"] == "u_probe_drift"

    r = client_no_raise.get(_BOOM, headers={"X-User-ID": "u_probe_drift"})
    assert r.status_code == 500

    rows = _events()
    assert len(rows) == 1
    assert rows[0][0] == "u_probe_drift"


# ---------- 9. 落库口径与中间件装配 ----------

def test_recorded_category_is_legal_enum(probe_routes):
    """category 写错会被 track_event 静默丢弃——所以这里同时断言它落在契约枚举内。"""
    client_no_raise.get(_BOOM_RESP)
    rows = _events()
    assert len(rows) == 1
    assert rows[0][1] == "ai_quality"
    assert rows[0][1] in ANALYTICS_CATEGORIES


def test_middleware_installed_on_app():
    """main.py 那一行 add_middleware 真的生效了（只断言装配，不触发请求）。"""
    assert HttpErrorTrackingMiddleware in [m.cls for m in app.user_middleware]


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/v1", True),
        ("/api/v1/plans", True),
        ("/api/v1/me/usage", True),
        ("/api/v1/analytics/events", True),
        ("/health", False),                       # 探活
        ("/assets/index-abc123.js", False),       # 静态资源
        ("/brand/logo-mark-on-light.png", False),  # 静态资源
        ("/docs", False),                         # 文档页
        ("/openapi.json", False),
        ("/settings", False),                     # SPA 回退路由
        ("/", False),
    ],
)
def test_should_track_path(path, expected):
    assert should_track_path(path) is expected

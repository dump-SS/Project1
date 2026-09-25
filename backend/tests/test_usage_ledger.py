"""usage_ledger 计量测试（G 板块 · #9/D38）——对应验收门「每次真实调用可追溯到用户数值成本」。

覆盖：
1. 真实 provider 调用成功 → usage_ledger 落行（tokens/成本/档位/模型名齐全）；
2. 供应商响应无 usage 字段 → 记 0 行（调用本身可追溯）；
3. context 缺 user_id → 不落行（成本无法归属，留给 AICallLog 审计）；
4. MockProvider（无真实成本）→ 不落行；
5. feature_tier 非法值 → 按 embedded 记；计价兜底（未登记模型走 FALLBACK）；
6. GET /me/usage：合计正确、按月过滤正确。
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import SessionLocal
from llm_provider import MockProvider, OpenAICompatibleProvider
from main import app
from models.governance import UsageLedger
from routes.governance import router as governance_router
from usage_ledger import compute_cost, record_usage

# main.py 的 router 挂载归 X0（共享文件独占表）；测试进程内按 main.py 同样的
# /api/v1 前缀挂上以便打接口，main.py 源文件不动，PR 里提供挂载片段由 X0 合入。
# ⚠️ main.py 的 SPA catch-all（/{full_path:path}）注册在前，会把测试进程内
# 后挂载的 GET 路由吞掉（路由匹配按注册顺序），必须插到它前面。
def _mount_governance_router() -> None:
    from main import app

    # 幂等：pytest 同进程跑多个测试模块时会重复 import 本文件逻辑
    if any(getattr(r, "path", "") == "/api/v1/me/usage" for r in app.router.routes):
        return
    routes = app.router.routes
    n = len(routes)
    app.include_router(governance_router, prefix="/api/v1")
    gov = routes[n:]
    del routes[n:]
    catch_idx = next(
        i for i, r in enumerate(routes) if getattr(r, "path", "") == "/{full_path:path}"
    )
    for j, r in enumerate(gov):
        routes.insert(catch_idx + j, r)


_mount_governance_router()

client = TestClient(app)


def _rows(user_id: str) -> list[UsageLedger]:
    db = SessionLocal()
    try:
        return (
            db.execute(select(UsageLedger).where(UsageLedger.user_id == user_id))
            .scalars()
            .all()
        )
    finally:
        db.close()


def _real_provider(monkeypatch, usage: dict | None) -> OpenAICompatibleProvider:
    """构造真实 provider 并打桩 _call_once（不发网络请求）。"""
    monkeypatch.setattr("llm_provider.settings.llm_api_key", "test-key")
    provider = OpenAICompatibleProvider()
    monkeypatch.setattr(
        provider, "_call_once", lambda url, payload, headers: ("好的", usage or {})
    )
    return provider


def test_real_call_records_usage_row(monkeypatch):
    provider = _real_provider(
        monkeypatch, {"prompt_tokens": 100, "completion_tokens": 50}
    )
    provider.generate("hi", context={
        "user_id": "u_ledger1", "feature_tier": "chat", "reasoning_tier": "standard",
    })

    rows = _rows("u_ledger1")
    assert len(rows) == 1
    row = rows[0]
    assert row.tokens_in == 100
    assert row.tokens_out == 50
    assert row.feature_tier == "chat"
    assert row.reasoning_tier == "standard"
    assert row.cost == pytest.approx(compute_cost(row.model, 100, 50))
    assert row.cost > 0, "真实调用必须有成本数值（可追溯）"


def test_missing_usage_field_still_records_zero_row(monkeypatch):
    provider = _real_provider(monkeypatch, None)
    provider.generate("hi", context={"user_id": "u_ledger2", "feature_tier": "embedded"})

    rows = _rows("u_ledger2")
    assert len(rows) == 1
    assert rows[0].tokens_in == 0 and rows[0].tokens_out == 0
    assert rows[0].feature_tier == "embedded"
    assert rows[0].reasoning_tier is None


def test_missing_user_id_skips_row(monkeypatch):
    provider = _real_provider(monkeypatch, {"prompt_tokens": 10, "completion_tokens": 5})
    provider.generate("hi", context={"feature_tier": "embedded"})  # 无 user_id
    provider.generate("hi", context=None)  # 无 context

    assert _rows("u_ledger_missing") == []
    db = SessionLocal()
    try:
        assert db.execute(select(UsageLedger)).scalars().all() == []
    finally:
        db.close()


def test_mock_provider_records_nothing():
    MockProvider().generate("hi", context={"user_id": "u_ledger3", "feature_tier": "chat"})
    assert _rows("u_ledger3") == []


def test_invalid_tier_falls_back_to_embedded(monkeypatch):
    record_usage({"user_id": "u_ledger4", "feature_tier": "not-a-tier"},
                 model="m", tokens_in=1, tokens_out=1)
    rows = _rows("u_ledger4")
    assert len(rows) == 1 and rows[0].feature_tier == "embedded"


def test_compute_cost_fallback_for_unknown_model():
    # MODEL_PRICING 为空 → 全部走 FALLBACK_PRICING = (2.0, 8.0) 元/1M tokens
    assert compute_cost("unknown-model", 1_000_000, 1_000_000) == pytest.approx(10.0)
    assert compute_cost("unknown-model", 0, 0) == 0.0


def test_usage_route_month_filter_and_totals():
    # 本月两笔 + 上月一笔
    record_usage({"user_id": "u_route1", "feature_tier": "chat"}, model="m1", tokens_in=1000, tokens_out=500)
    record_usage({"user_id": "u_route1", "feature_tier": "embedded"}, model="m1", tokens_in=200, tokens_out=100)

    db = SessionLocal()
    try:
        db.add(UsageLedger(
            id="ul_lastmonth", user_id="u_route1", feature_tier="chat",
            reasoning_tier=None, model="m1", tokens_in=999, tokens_out=999, cost=9.99,
            created_at=datetime(2020, 1, 15),
        ))
        db.commit()
    finally:
        db.close()

    # 缺省当月：不含上月的 999
    r = client.get("/api/v1/me/usage", headers={"X-User-ID": "u_route1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2
    assert body["totalTokensIn"] == 1200
    assert body["totalTokensOut"] == 600
    assert body["totalCost"] == pytest.approx(sum(i["cost"] for i in body["items"]))

    # 显式指定上月：只有那一笔
    r = client.get("/api/v1/me/usage", params={"month": "2020-01"}, headers={"X-User-ID": "u_route1"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["tokensIn"] == 999

    # 不下发 userId（资源以当前用户为作用域）
    assert all("userId" not in i and "user_id" not in i for i in body["items"])

    # 他人数据不可见
    r = client.get("/api/v1/me/usage", headers={"X-User-ID": "u_route2"})
    assert r.status_code == 200 and r.json()["items"] == []

    # month 格式非法 → 400 VALIDATION_FAILED
    r = client.get("/api/v1/me/usage", params={"month": "2020/01"}, headers={"X-User-ID": "u_route1"})
    assert r.status_code == 400

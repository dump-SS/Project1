"""#29b「将个人数据用于提升体验」开关测试（默认关闭 / opt-in）。

该开关承载页是「设置 → 授权与隐私」（D41/D42），本模块验证后端语义：
1. GET 默认 false（未显式开启前不进入产品改进用途）
2. PATCH 开启 / 关闭，返回值与持久化一致
3. 与其它设置字段互不干扰（至少传一项的校验含新字段）
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

HDR = {"X-User-ID": "u_improvement_toggle"}


def test_default_is_off():
    """默认关闭（opt-in）——这是 #29b 的硬口径。"""
    r = client.get("/api/v1/me/settings", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["experienceImprovementEnabled"] is False


def test_enable_then_disable_persists():
    """开启 → 读取为 true；关闭 → 读取为 false。"""
    r = client.patch(
        "/api/v1/me/settings",
        json={"experienceImprovementEnabled": True},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["experienceImprovementEnabled"] is True

    assert client.get("/api/v1/me/settings", headers=HDR).json()["experienceImprovementEnabled"] is True

    r2 = client.patch(
        "/api/v1/me/settings",
        json={"experienceImprovementEnabled": False},
        headers=HDR,
    )
    assert r2.json()["experienceImprovementEnabled"] is False
    assert client.get("/api/v1/me/settings", headers=HDR).json()["experienceImprovementEnabled"] is False


def test_other_settings_untouched():
    """改新字段不影响旧字段（且新字段单独传也满足「至少传一项」）。"""
    before = client.get("/api/v1/me/settings", headers=HDR).json()

    r = client.patch(
        "/api/v1/me/settings",
        json={"experienceImprovementEnabled": True},
        headers=HDR,
    )
    after = r.json()
    assert after["aiWeightTuningEnabled"] == before["aiWeightTuningEnabled"]
    assert after["sendTextToAI"] == before["sendTextToAI"]
    assert after["knowledgeAiEgressEnabled"] == before["knowledgeAiEgressEnabled"]


def test_empty_body_still_rejected():
    """空 body 仍被拒（至少传一项）。"""
    r = client.patch("/api/v1/me/settings", json={}, headers=HDR)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"

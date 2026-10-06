"""用户内容 embedding API 出域开关（PRD 12.6 / D41）—— 授权、守门与出域判定测试。

对应契约 `Settings.userContentEmbeddingApiEnabled` / `PATCH /me/settings`。

**四条硬约束**（brief 明确「没有空间」，本文件逐条守住）：
1. 默认关：没 opt-in 时用户内容**恒定本地**、绝不出域；
2. 未成年且监护人授权未生效 → 开启被 403（未授权 REQUIRED / 已失效 EXPIRED）；
3. 撤回（置 false）是用户权利，**不受授权状态限制**；
4. 本地模型缺失时**绝不自动改走 api**（宁缺毋滥，D34）。

形状照 `tests/test_community_consent.py`（D41 守门的现成先例）。
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import embedding_service
from config import settings
from database import SessionLocal
from egress_guard import EMBED_SRC_KB, EMBED_SRC_USER, EgressViolation
from egress_guard import assert_embed_source_offdomain_allowed as assert_allowed
from main import app
from models.user import GuardianAuthorization as GuardianORM
from models.user import Settings as SettingsORM
from models.user import User as UserORM

client = TestClient(app)

UID = "u_uc_emb_test"
HDR = {"X-User-ID": UID}


def _clean() -> None:
    """清掉本用例用到的三类行，保证用例间隔离。"""
    db = SessionLocal()
    try:
        for model in (SettingsORM, GuardianORM, UserORM):
            row = db.get(model, UID)
            if row is not None:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def _set_user(birth_year: int | None) -> None:
    """建/改用户行。`birth_year=None` 模拟**存量账号**（既有约定：不拦截）。"""
    db = SessionLocal()
    try:
        row = db.get(UserORM, UID)
        if row is None:
            row = UserORM(
                id=UID, email=f"{UID}@epochx.dev", stage="senior", grade="",
                subjects=["other"], onboarding_completed=False,
            )
            db.add(row)
        row.birth_year = birth_year
        db.commit()
    finally:
        db.close()


def _grant_guardian(status_value: str) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuardianORM, UID)
        if row is None:
            row = GuardianORM(user_id=UID)
            db.add(row)
        row.status = status_value
        db.commit()
    finally:
        db.close()


def _patch(value: bool):
    return client.patch(
        "/api/v1/me/settings", json={"userContentEmbeddingApiEnabled": value}, headers=HDR
    )


# ========== 第 1 条硬约束：默认关 = 用户内容不出域 ==========

def test_default_off_user_content_stays_local_and_cannot_egress():
    """没 opt-in → 模式恒为 local；EgressGuard 也必须拦（默认拒绝）。"""
    _clean()
    assert embedding_service.embed_mode_for(EMBED_SRC_USER) == "local"
    # 即便全局配成 api，用户内容依然 local（这是「不随配置出域」的本体）
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "kb_embed_mode", "api")
        assert embedding_service.embed_mode_for(EMBED_SRC_USER) == "local"
        assert embedding_service.embed_mode_for(EMBED_SRC_USER, user_api_opt_in=False) == "local"
    # EgressGuard 默认拒绝用户内容出域
    with pytest.raises(EgressViolation):
        assert_allowed(EMBED_SRC_USER)
    # 知识库内容不受影响（仍然允许）
    assert_allowed(EMBED_SRC_KB)


def test_settings_default_value_is_false():
    """契约 required + 默认 false：GET 回来必须是 false。"""
    _clean()
    r = client.get("/api/v1/me/settings", headers=HDR)
    assert r.status_code == 200
    assert r.json()["userContentEmbeddingApiEnabled"] is False


# ========== 第 2 条：opt-in 后才允许走 api ==========

def test_opt_in_allows_api_mode_and_egress(monkeypatch):
    """opt-in + 全局 api → 用户内容才跟随走 api，EgressGuard 也放行。"""
    _clean()
    monkeypatch.setattr(settings, "kb_embed_mode", "api")
    assert embedding_service.embed_mode_for(EMBED_SRC_USER, user_api_opt_in=True) == "api"
    assert_allowed(EMBED_SRC_USER, user_api_opt_in=True)  # 不抛

    called = {}

    def _fake_api(text):
        called["api"] = text
        return [0.1] * 512

    monkeypatch.setattr(embedding_service, "_embed_api", _fake_api)
    monkeypatch.setattr(embedding_service, "_embed_local", lambda t: pytest.fail("不该走本地"))
    assert embedding_service.embed_text(
        "错题原文", source=EMBED_SRC_USER, user_api_opt_in=True
    ) is not None
    assert called["api"] == "错题原文"


def test_opt_in_but_global_local_still_local(monkeypatch):
    """opt-in 只是「允许」，不改变后端选型：全局是 local 就还是 local。"""
    _clean()
    monkeypatch.setattr(settings, "kb_embed_mode", "local")
    assert embedding_service.embed_mode_for(EMBED_SRC_USER, user_api_opt_in=True) == "local"


# ========== 第 4 条硬约束：本地缺失绝不自动改走 api ==========

def test_local_missing_never_falls_back_to_api(monkeypatch):
    """本地模型不可用 → 返回 None（调用方降级 name_fuzzy），**绝不改走 api**（D34）。"""
    _clean()
    monkeypatch.setattr(settings, "kb_embed_mode", "api")  # 全局本来是 api
    monkeypatch.setattr(embedding_service, "_embed_local", lambda t: None)
    monkeypatch.setattr(
        embedding_service, "_embed_api", lambda t: pytest.fail("本地缺失时绝不该走 api")
    )
    # 未 opt-in：模式被钉死 local → 本地失败 → None
    assert embedding_service.embed_text("错题原文", source=EMBED_SRC_USER) is None
    assert embedding_service.embed_text(
        "错题原文", source=EMBED_SRC_USER, user_api_opt_in=False
    ) is None


# ========== 第 2 条硬约束：未成年 + 未授权 → 403 ==========

def _under14_birth_year() -> int:
    return date.today().year - 14  # 差 14 → 保守判为「可能未满 14 周岁」


def test_underage_without_guardian_cannot_enable_required():
    _clean()
    _set_user(_under14_birth_year())
    r = _patch(True)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_REQUIRED"


def test_underage_with_expired_guardian_cannot_enable_expired():
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("expired")
    r = _patch(True)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_EXPIRED"


def test_underage_with_revoked_guardian_cannot_enable_expired():
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("revoked")
    r = _patch(True)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_EXPIRED"


def test_underage_with_active_guardian_can_enable():
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("active")
    r = _patch(True)
    assert r.status_code == 200
    assert r.json()["userContentEmbeddingApiEnabled"] is True


def test_adult_without_guardian_record_can_enable():
    """成年（含 birth_year 为 None 的存量账号）**不被**授权状态拦——这是与 community.py 守门的关键差别。"""
    _clean()
    _set_user(None)  # 存量账号：birth_year 未知 → 既有约定不拦
    r = _patch(True)
    assert r.status_code == 200
    assert r.json()["userContentEmbeddingApiEnabled"] is True

    _clean()
    _set_user(date.today().year - 30)  # 明确成年
    r = _patch(True)
    assert r.status_code == 200


# ========== 第 3 条硬约束：撤回不被授权状态拦 ==========

def test_revoke_is_never_blocked_by_guardian_status():
    """先合法开启，再把授权置失效 → 撤回（false）仍必须成功（撤回是权利）。"""
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("active")
    assert _patch(True).status_code == 200

    _grant_guardian("expired")  # 授权失效
    r = _patch(False)
    assert r.status_code == 200, r.text
    assert r.json()["userContentEmbeddingApiEnabled"] is False

    _grant_guardian("revoked")
    assert _patch(False).status_code == 200


def test_settings_update_at_least_one_includes_new_field():
    """新字段要进 _at_least_one 校验：只传它一项也算合法。"""
    _clean()
    r = client.patch(
        "/api/v1/me/settings", json={"userContentEmbeddingApiEnabled": False}, headers=HDR
    )
    assert r.status_code == 200

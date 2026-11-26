"""带图出域门控（A1，2026-11-27 Skyer 复核）测试。

守四条：
1. 开关关 + 未带 ``X-Egress-Confirm`` → **428 EGRESS_CONFIRM_REQUIRED**（各带图入口）；
2. 开关关 + 带确认 → 放行本次（单次授权）；
3. 开关开 → 不需要确认（持久授权）；
4. 未满 14 岁 + 监护人授权未生效 → 开启 ``knowledgeAiEgressEnabled`` 被 403（D41），
   但**撤回（false）永不被挡**——否则授权一失效用户连关都关不掉。

为什么端点是这四个：门控挂在路由层（能拿 DB + 请求头），不在 chat_engine /
worksheet_extract；``chat_jobs`` 的 worker 没有请求上下文，重试必须在入队前完成。
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from egress_gate import (
    EGRESS_CONFIRM_HEADER,
    EGRESS_CONFIRM_REQUIRED,
    is_confirmed,
    require_egress_consent,
)
from main import app
from models.user import GuardianAuthorization as GuardianORM
from models.user import Settings as SettingsORM
from models.user import User as UserORM

client = TestClient(app)

UID = "u_egress_gate_test"
HDR = {"X-User-ID": UID}
MEDIA_KEY = f"user/{UID}/probe.png"


def _clean() -> None:
    db = SessionLocal()
    try:
        for model in (SettingsORM, GuardianORM, UserORM):
            row = db.get(model, UID)
            if row is not None:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def _set_switch(enabled: bool) -> None:
    db = SessionLocal()
    try:
        row = db.get(SettingsORM, UID)
        if row is None:
            row = SettingsORM(
                user_id=UID,
                ai_weight_tuning_enabled=True,
                send_text_to_ai=False,
                knowledge_ai_egress_enabled=enabled,
                community_consent_enabled=False,
                community_auto_participate=True,
            )
            db.add(row)
        else:
            row.knowledge_ai_egress_enabled = enabled
        db.commit()
    finally:
        db.close()


def _set_user(birth_year: int | None) -> None:
    db = SessionLocal()
    try:
        row = db.get(UserORM, UID)
        if row is None:
            row = UserORM(
                id=UID,
                email=f"{UID}@epochx.dev",
                stage="senior",
                grade="",
                subjects=["other"],
                onboarding_completed=False,
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


def _consent(confirmed_header: str | None) -> None:
    db = SessionLocal()
    try:
        require_egress_consent(
            db,
            UID,
            confirmed=is_confirmed(confirmed_header),
            scene="unit",
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 一、门控单元：三种输入组合
# ---------------------------------------------------------------------------

def test_switch_off_without_confirm_raises_428():
    _clean()
    _set_switch(False)
    with pytest.raises(Exception) as ei:
        _consent(None)
    assert getattr(ei.value, "status_code", None) == 428
    assert ei.value.detail["code"] == EGRESS_CONFIRM_REQUIRED


def test_switch_off_with_confirm_passes():
    _clean()
    _set_switch(False)
    _consent("1")  # 不抛即通过


def test_switch_on_passes_without_confirm():
    _clean()
    _set_switch(True)
    _consent(None)  # 持久授权，无需每次确认


@pytest.mark.parametrize("bad", ["0", "true", "", "  ", "yes"])
def test_bad_confirm_value_counts_as_unconfirmed(bad: str):
    _clean()
    _set_switch(False)
    with pytest.raises(Exception) as ei:
        _consent(bad)
    assert getattr(ei.value, "status_code", None) == 428


# ---------------------------------------------------------------------------
# 二、端点：开关关时必须 428，且错误码可被前端识别
# ---------------------------------------------------------------------------

def test_chat_media_requires_confirm():
    _clean()
    _set_switch(False)
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "这题怎么做", "mediaKey": MEDIA_KEY},
        headers=HDR,
    )
    assert r.status_code == 428, r.text
    assert r.json()["error"]["code"] == EGRESS_CONFIRM_REQUIRED


def test_chat_media_with_confirm_enqueues(monkeypatch):
    """带确认后必须真的放行到入队（202），不是"换个错误码继续拦"。"""
    _clean()
    _set_switch(False)
    import routes.chat as chat_route

    monkeypatch.setattr(chat_route, "run_chat_job", lambda job_id: None)
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "这题怎么做", "mediaKey": MEDIA_KEY},
        headers={**HDR, EGRESS_CONFIRM_HEADER: "1"},
    )
    assert r.status_code == 202, r.text


def test_chat_media_switch_on_passes_without_confirm(monkeypatch):
    _clean()
    _set_switch(True)
    import routes.chat as chat_route

    monkeypatch.setattr(chat_route, "run_chat_job", lambda job_id: None)
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "这题怎么做", "mediaKey": MEDIA_KEY},
        headers=HDR,
    )
    assert r.status_code == 202, r.text


def test_worksheet_requires_confirm():
    _clean()
    _set_switch(False)
    r = client.post(
        "/api/v1/f/worksheet/extract",
        json={"mediaKey": MEDIA_KEY},
        headers=HDR,
    )
    assert r.status_code == 428, r.text
    assert r.json()["error"]["code"] == EGRESS_CONFIRM_REQUIRED


def test_media_summary_requires_confirm():
    _clean()
    _set_switch(False)
    r = client.post(f"/api/v1/f/media/{MEDIA_KEY}/summary", headers=HDR)
    assert r.status_code == 428, r.text
    assert r.json()["error"]["code"] == EGRESS_CONFIRM_REQUIRED


# ---------------------------------------------------------------------------
# 三、D41：开启开关的未成年人门槛；撤回永不被挡
# ---------------------------------------------------------------------------

def _patch_egress(value: bool):
    return client.patch(
        "/api/v1/me/settings",
        json={"knowledgeAiEgressEnabled": value},
        headers=HDR,
    )


def _under14_birth_year() -> int:
    return date.today().year - 14


def test_under14_without_guardian_cannot_enable_egress():
    _clean()
    _set_user(_under14_birth_year())
    r = _patch_egress(True)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_REQUIRED"


def test_under14_with_expired_guardian_cannot_enable_egress():
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("expired")
    r = _patch_egress(True)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "GUARDIAN_AUTHORIZATION_EXPIRED"


def test_under14_with_active_guardian_can_enable_egress():
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("active")
    r = _patch_egress(True)
    assert r.status_code == 200, r.text
    assert r.json()["knowledgeAiEgressEnabled"] is True


def test_revoke_egress_is_never_blocked():
    """撤回（false）是用户权利：授权过期也必须能关掉。"""
    _clean()
    _set_user(_under14_birth_year())
    _grant_guardian("expired")
    _set_switch(True)
    r = _patch_egress(False)
    assert r.status_code == 200, r.text
    assert r.json()["knowledgeAiEgressEnabled"] is False


def test_adult_without_guardian_record_can_enable_egress():
    """成年 / 存量账号（birth_year=None）不被授权状态拦。"""
    _clean()
    _set_user(None)
    r = _patch_egress(True)
    assert r.status_code == 200, r.text
    assert r.json()["knowledgeAiEgressEnabled"] is True

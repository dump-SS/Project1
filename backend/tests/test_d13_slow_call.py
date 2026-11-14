"""矩阵 D13 · 慢 LLM 调用窗口辅助写丢失的回归测试（PRD 6.5 / 铁律 5）。

## 缺陷本体（x2-degradation-matrix-verified.md D13 + E2E §2.2，2026-10-30 实测）

主 session 在 generate 前的挂起写（`_get_or_create_session` 的 flush INSERT）让
**整个慢 LLM 调用窗口持有 SQLite RESERVED 写锁**——辅助写（ai_call_logs /
usage_ledger，各自独立 SessionLocal）的 INSERT 撞锁，busy timeout 5s 后 ROLLBACK，
**留痕与真实用量双双丢失**，且失败当时被 logger.debug 吞掉（25d65a1 已提 warning，
本单修竞争本体）。

## 修法（两层，均为本测试锁定）

1. chat_engine 两处 generate 前先 `db.commit()` 落盘挂起写——慢窗口**零持锁**；
2. 辅助写（ai_call_log._persist / usage_ledger.record_usage）**失败重试一次**
   （0.3s 短退避）——即便撞上残余竞争也能落。失败 warning 不静默；
   busy_timeout 不调大（派单红线）。

## 断言纪律（派单 §四）

查库断言行数与字段，不许只测「函数被调用」。真实行断言 tokens 为**供应商真实
回报值**（11/7），与 len//4 估算值（约 5/…）天然可区分。
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import chat_engine
import llm_provider
import usage_ledger
from config import settings
from database import SessionLocal
from models.ai_call_log import AICallLog
from models.governance import UsageLedger

UID = "u_d13"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


@pytest.fixture
def slow_real_provider(monkeypatch, request):
    """真 OpenAICompatibleProvider + 打桩 _call_once：延迟可控、无网络。

    request.param：("success", delay) / ("none", delay) / ("raise", delay)
    —— "none" 模拟网关失败（真实 _call_once 吞异常返回 None 的行为）。
    get_provider 的两处绑定（chat_engine 模块级 / safety_filter 函数内）都指向它。
    """
    mode, delay = request.param
    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    from llm_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider()

    def fake_call(url, payload, headers):
        if delay:
            time.sleep(delay)
        if mode == "success":
            return "好的", {"prompt_tokens": 11, "completion_tokens": 7}
        if mode == "none":
            return None, {}
        if mode == "raise":
            raise TimeoutError("simulated gateway timeout")
        raise ValueError(f"unknown mode {mode}")

    monkeypatch.setattr(provider, "_call_once", fake_call)

    import llm_provider as lp

    monkeypatch.setattr(chat_engine, "get_provider", lambda: provider)
    monkeypatch.setattr(lp, "get_provider", lambda: provider)
    return provider


def _call_rows(user_id: str) -> list[AICallLog]:
    db = SessionLocal()
    try:
        return db.query(AICallLog).filter(AICallLog.function_type == "chat").all()
    finally:
        db.close()


def _usage_rows(user_id: str) -> list[UsageLedger]:
    db = SessionLocal()
    try:
        return db.query(UsageLedger).filter(UsageLedger.user_id == user_id).all()
    finally:
        db.close()


def _ephemeral(db, content: str = "帮我看看这道题怎么解"):
    """直调随手问：内部有 session upsert（generate 前的挂起写来源）。"""
    return chat_engine.handle_ephemeral(db, UID, content)


# ---------------------------------------------------------------- 慢调用成功


@pytest.mark.parametrize("slow_real_provider", [("success", 0.4)], indirect=True)
def test_slow_success_both_rows_landed(client, slow_real_provider):
    """慢调用成功：ai_call_logs 留痕 + usage_ledger 真实行都落库，user_id 非空、单行。"""
    db = SessionLocal()
    try:
        _ephemeral(db)
        db.commit()
    finally:
        db.close()

    calls = _call_rows(UID)
    assert len(calls) == 1, f"留痕应恰 1 行，实际 {len(calls)}"
    assert calls[0].success is True

    usage = _usage_rows(UID)
    assert len(usage) == 1, f"真实用量应恰 1 行（真实+估算不并存），实际 {len(usage)}"
    assert usage[0].user_id == UID
    assert usage[0].tokens_in == 11 and usage[0].tokens_out == 7  # 供应商真实回报值


# ---------------------------------------------------------------- 慢调用失败


@pytest.mark.parametrize("slow_real_provider", [("none", 0.4)], indirect=True)
def test_slow_gateway_failure_leaves_trace_and_estimate(client, slow_real_provider):
    """网关失败（generate=None）：ai_call_logs 失败留痕行落库；usage_ledger 无真实行
    ——账不造假，但留痕不缺（PRD 6.5）。"""
    db = SessionLocal()
    try:
        _ephemeral(db)
        db.commit()
    finally:
        db.close()

    calls = _call_rows(UID)
    assert len(calls) == 1
    assert calls[0].success is False
    assert calls[0].error_msg == "retries_exhausted"

    # 失败调用没有真实 tokens 可记——usage_ledger 不造假流水（lead 口径：
    # 「某条路径压根不调真模型/失败，如实报，别硬造」）
    assert _usage_rows(UID) == []


# ---------------------------------------------------------------- 慢调用异常


@pytest.mark.parametrize("slow_real_provider", [("raise", 0.4)], indirect=True)
def test_slow_provider_raises_exception_propagates(client, slow_real_provider):
    """打桩直接抛 TimeoutError（穿透 generate，与真实 _call_once 的吞行为不同）：
    异常向上冒泡；此时 provider 层留痕/记账尚未来得及发生——如实断言，不假装有账。"""
    db = SessionLocal()
    try:
        with pytest.raises(TimeoutError):
            _ephemeral(db)
        db.commit()
    finally:
        db.close()

    # 异常路径下 provider 层的留痕/记账都未发生（不是「丢了」而是「没发生」）
    assert _call_rows(UID) == []
    assert _usage_rows(UID) == []


# ---------------------------------------------------------------- 回归


def test_fast_stubbed_calls_five_of_five(client, monkeypatch):
    """快调用（无延迟）连发 5 条：ai_call_logs 5/5、usage_ledger 5/5 全部落库
    （矩阵 A13 的回归锁）。"""
    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    from llm_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider()

    def fake_call(url, payload, headers):
        return "好的", {"prompt_tokens": 11, "completion_tokens": 7}

    monkeypatch.setattr(provider, "_call_once", fake_call)
    import llm_provider as lp

    monkeypatch.setattr(chat_engine, "get_provider", lambda: provider)
    monkeypatch.setattr(lp, "get_provider", lambda: provider)

    db = SessionLocal()
    try:
        for _ in range(5):
            _ephemeral(db)
        db.commit()
    finally:
        db.close()

    assert len(_call_rows(UID)) == 5
    usage = _usage_rows(UID)
    assert len(usage) == 5, f"5 次快调用应 5 行真实用量（不重复、不丢失），实际 {len(usage)}"
    assert all(u.user_id == UID for u in usage)

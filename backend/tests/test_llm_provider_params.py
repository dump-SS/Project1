"""2026-10-18：生成参数可配置 + 空串显式失败 + record_usage 真实计量。

三个 brief 点的回归：

1. ``llm_max_tokens`` / ``llm_temperature`` / ``llm_request_timeout`` 都走 settings，
   而不是 llm_provider 里的硬编码字面量。
2. **空串 = 失败**：原判据是 ``text is not None``，推理模型烧光 max_tokens、
   ``finish_reason='length'``、``content=''`` 会被当成成功——``log_call`` 记
   ``success=True``，日志上完全看不出问题，上层 ``if not llm_text`` 回落兜底话术。
   生产实测带图提问 20 次里 7 次这样（35%）。现在空串走重试。
3. ``record_usage`` 只在拿到 ``user_id`` 时才写行（否则 no-op），且写成功后置线程
   局部标记，调用方据此不再补 len//4 估算行。
"""

from __future__ import annotations

import logging

import pytest

import llm_provider
from config import settings


# --------------------------------------------------------------------------
# 1. 生成参数 / 超时走 settings
# --------------------------------------------------------------------------


def test_generation_params_come_from_settings(monkeypatch):
    """payload 里的 max_tokens / temperature 必须取自 settings，不是硬编码。"""
    import json
    import urllib.request

    captured: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}],"usage":{}}'

    def _fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["payload_bytes"] = req.data
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr(settings, "llm_max_tokens", 4096)
    monkeypatch.setattr(settings, "llm_temperature", 0.3)
    monkeypatch.setattr("usage_ledger.record_usage", lambda *a, **k: None)

    p = llm_provider.OpenAICompatibleProvider.__new__(llm_provider.OpenAICompatibleProvider)
    p.MAX_RETRIES = 0
    p.generate("hi", context={"user_id": "u_param_1"})

    payload = captured["payload"]
    assert payload["max_tokens"] == 4096, "max_tokens 应来自 settings"
    assert payload["temperature"] == pytest.approx(0.3), "temperature 应来自 settings"

    # 改配置 -> payload 跟着变，证明不是硬编码
    monkeypatch.setattr(settings, "llm_max_tokens", 777)
    p.generate("hi", context={"user_id": "u_param_1"})
    assert json.loads(captured["payload_bytes"].decode("utf-8"))["max_tokens"] == 777


def test_request_timeout_used_in_call(monkeypatch):
    """_call_once 必须用 settings.llm_request_timeout，而不是类属性 60。"""
    seen: list[object] = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":2}}'

    import urllib.request

    def _fake_urlopen(req, timeout=None):
        seen.append(timeout)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(settings, "llm_request_timeout", 7)

    p = llm_provider.OpenAICompatibleProvider.__new__(llm_provider.OpenAICompatibleProvider)
    text, usage = p._call_once("http://x", b"{}", {})
    assert text == "ok"
    assert usage == {"prompt_tokens": 1, "completion_tokens": 2}
    assert seen == [7], f"urlopen 应该收到配置的 7 秒，实际收到 {seen}"


# --------------------------------------------------------------------------
# 2. 空串显式失败
# --------------------------------------------------------------------------


def _provider_with(monkeypatch, texts: list[str | None]) -> llm_provider.OpenAICompatibleProvider:
    """造一个 _call_once 按 texts 依次返回的 provider。"""
    p = llm_provider.OpenAICompatibleProvider.__new__(llm_provider.OpenAICompatibleProvider)
    seq = list(texts)

    def _fake(url, payload, headers):
        value = seq.pop(0) if seq else None
        return value, {"prompt_tokens": 7, "completion_tokens": 9}

    p._call_once = _fake  # type: ignore[method-assign]
    p.MAX_RETRIES = 1
    return p


def test_empty_string_is_treated_as_failure_and_retried(monkeypatch):
    """第一次空串 -> 不算成功，继续重试；第二次拿到正文 -> 成功。"""
    calls: list[tuple] = []

    def _fake_log_call(context, latency_ms, success, error_msg=None):
        calls.append((success, error_msg))

    import ai_call_log

    monkeypatch.setattr(ai_call_log, "log_call", _fake_log_call)
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("usage_ledger.record_usage", lambda *a, **k: None)

    p = _provider_with(monkeypatch, ["", " 真实回复"])
    out = p.generate("hi", context={"user_id": "u1"})

    assert out == " 真实回复", "空串后重试拿到正文，应返回正文"
    assert calls == [(True, None)], f"只应记一次成功，实际 {calls}"


def test_empty_string_on_first_attempt_still_recovers(monkeypatch):
    """空串 + 供应商报 usage 时也要能重试，不能直接返回 ''。"""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("usage_ledger.record_usage", lambda *a, **k: None)

    import ai_call_log

    monkeypatch.setattr(ai_call_log, "log_call", lambda *a, **k: None)

    p = _provider_with(monkeypatch, ["", "second"])
    assert p.generate("hi", context={"user_id": "u1"}) == "second"


def test_all_attempts_empty_returns_none_and_logs_failure(monkeypatch):
    """两次都空串 -> 返回 None（上层兜底话术），且 log_call 记 success=False。"""
    calls: list[tuple] = []
    import ai_call_log

    monkeypatch.setattr(
        ai_call_log, "log_call", lambda c, latency_ms, success, error_msg=None: calls.append((success, error_msg))
    )
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)

    p = _provider_with(monkeypatch, ["", "   "])
    out = p.generate("hi", context={"user_id": "u1"})

    assert out is None, "全空必须返回 None，不能返回空串"
    assert calls == [(False, "retries_exhausted")], f"应记一次失败，实际 {calls}"


def test_none_return_is_still_failure(monkeypatch):
    """供应商抛错返回 None 的老路径不变：失败 + retries_exhausted。"""
    calls: list[tuple] = []
    import ai_call_log

    monkeypatch.setattr(
        ai_call_log, "log_call", lambda c, latency_ms, success, error_msg=None: calls.append((success, error_msg))
    )
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)

    p = _provider_with(monkeypatch, [None, None])
    assert p.generate("hi", context={"user_id": "u1"}) is None
    assert calls == [(False, "retries_exhausted")]


# --------------------------------------------------------------------------
# 3. record_usage：拿不到 user_id 是 no-op，拿到就写行 + 置标记
# --------------------------------------------------------------------------


def test_record_usage_is_noop_without_user_id():
    """边界不变：context 无 user_id 时不写行（这是原行为，防脏数据）。"""
    import usage_ledger

    usage_ledger.begin_call()
    usage_ledger.record_usage({}, model="m", tokens_in=10, tokens_out=5)
    assert usage_ledger.recorded_real_usage() is False


def test_record_usage_sets_flag_when_row_written():
    """拿到 user_id 就写行并置位，供调用方跳过估算行。"""
    from sqlalchemy import select

    import usage_ledger
    from database import SessionLocal
    from models.governance import UsageLedger

    usage_ledger.begin_call()
    assert usage_ledger.recorded_real_usage() is False

    usage_ledger.record_usage(
        {"user_id": "u_flag_1", "feature_tier": "multimodal"},
        model="m",
        tokens_in=11,
        tokens_out=7,
    )
    assert usage_ledger.recorded_real_usage() is True, "写行成功后必须置位"

    db = SessionLocal()
    try:
        rows = db.execute(select(UsageLedger).where(UsageLedger.user_id == "u_flag_1")).scalars().all()
        assert len(rows) == 1
        # 真实 token，而不是 len//4 估算
        assert rows[0].tokens_in == 11
        assert rows[0].tokens_out == 7
        assert rows[0].feature_tier == "multimodal"
    finally:
        db.close()


def test_begin_call_resets_flag():
    """begin_call 清标记，避免上一轮置位污染下一轮。"""
    import usage_ledger

    usage_ledger.begin_call()
    usage_ledger.record_usage({"user_id": "u_flag_2"}, model="m", tokens_in=1, tokens_out=1)
    assert usage_ledger.recorded_real_usage() is True
    usage_ledger.begin_call()
    assert usage_ledger.recorded_real_usage() is False


def test_flag_is_thread_local():
    """并发安全：标记必须是线程局部，不能是全局。"""
    import threading

    import usage_ledger

    usage_ledger.begin_call()
    usage_ledger.record_usage({"user_id": "u_flag_3"}, model="m", tokens_in=1, tokens_out=1)
    assert usage_ledger.recorded_real_usage() is True

    seen: list[bool] = []

    def _worker():
        seen.append(usage_ledger.recorded_real_usage())

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    assert seen == [False], "另一个线程不该看到本线程的标记"


# --------------------------------------------------------------------------
# 4. max_tokens 默认 8192（2026-10-18 生产复测 15% 失败后调整）
# --------------------------------------------------------------------------


def test_max_tokens_default_is_8192():
    """8192 的依据：PR #63 上线后 20 次复测，3 次失败全是两次都烧光 4096。

    usage_ledger 里 tokens_out 最大值正好等于当时 max_tokens(4096)，坐实顶到天花板；
    且那 3 次只耗时 91~96s，远没到 180s 超时线，所以不可能是超时。
    """
    assert settings.llm_max_tokens == 8192


# --------------------------------------------------------------------------
# 5. 「重试成功 / 生成成功」必须是 WARNING 级（可观测性红线）
# --------------------------------------------------------------------------


def _run_and_capture(caplog, monkeypatch, texts):
    import ai_call_log

    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("usage_ledger.record_usage", lambda *a, **k: None)
    monkeypatch.setattr(ai_call_log, "log_call", lambda *a, **k: None)

    p = _provider_with(monkeypatch, texts)
    with caplog.at_level(logging.DEBUG, logger="llm_provider"):
        return p.generate("hi", context={"user_id": "u_lvl"})


def test_success_log_is_warning_level(caplog, monkeypatch):
    """⚠️ 这条是**可观测性红线**，不是风格问题。

    Railway 只持久化 WARNING 及以上；INFO 级的「生成成功」在容器日志里根本不存在。
    上一轮「6 次靠重试救回」只能靠算术推导（空串数 - 耗尽数 x 2）算出来，
    就是因为这条被降在 INFO 上没人看见。

    如果哪天有人「清理日志噪音」把它改回 info，这条测试会红——那正是它存在的意义。
    """
    _run_and_capture(caplog, monkeypatch, ["正常回复"])

    hits = [r for r in caplog.records if "生成成功" in r.getMessage()]
    assert len(hits) == 1, f"应记录一次生成成功，实际 {len(hits)} 条"
    assert hits[0].levelno >= logging.WARNING, (
        f"「生成成功」当前是 {hits[0].levelname}，Railway 不持久化 INFO，"
        "等于把这条数据藏起来了"
    )


def test_retry_success_log_is_warning_level(caplog, monkeypatch):
    """同上：「重试成功」必须 WARNING，否则「重试救回次数」永远只能推导不能观测。"""
    _run_and_capture(caplog, monkeypatch, ["", "重试后拿到的正文"])

    hits = [r for r in caplog.records if "重试成功" in r.getMessage()]
    assert len(hits) == 1, f"应记录一次重试成功，实际 {len(hits)} 条"
    assert hits[0].levelno >= logging.WARNING, (
        f"「重试成功」当前是 {hits[0].levelname}，Railway 不持久化 INFO，"
        "「空串->重试」这条机制就变成了看不见的黑盒"
    )

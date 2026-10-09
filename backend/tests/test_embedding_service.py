"""embedding_service 测试（S0-T7：第三方 API 分支 + 降级语义）。

覆盖：
- api 模式正常返回向量（mock HTTP 响应）
- api 模式配置缺失 → None（name_fuzzy 降级）
- api 模式 HTTP 异常 → None，不抛错
- off 模式 → None
- **合规双链路**（2026-09-27 补，PRD 12.6 / AGENTS.md 铁律 6）：
  知识库内容可出域；**用户内容（错题/学习记录）强制本地、永不出域**，
  且本地不可用时宁缺毋滥不向量。
"""
from __future__ import annotations

import json

import pytest

import embedding_service
from config import settings
from egress_guard import (
    EMBED_SRC_KB,
    EMBED_SRC_USER,
    EgressViolation,
    assert_embed_source_offdomain_allowed,
)


class _FakeUrlopen:
    def __init__(self, body: dict, exc: Exception | None = None):
        self._body = body
        self._exc = exc

    def __enter__(self):
        if self._exc is not None:
            raise self._exc
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")


def _set_api_config(monkeypatch, key="sk-test", base_url="https://embed.example.com/v1", model="test-embed"):
    monkeypatch.setattr(settings, "kb_embed_mode", "api")
    monkeypatch.setattr(settings, "embed_api_key", key)
    monkeypatch.setattr(settings, "embed_base_url", base_url)
    monkeypatch.setattr(settings, "embed_model", model)


def test_embed_api_returns_vector(monkeypatch):
    _set_api_config(monkeypatch)
    calls: list[dict] = []

    def fake_urlopen(req, timeout):
        calls.append({"url": req.full_url, "timeout": timeout})
        return _FakeUrlopen({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    monkeypatch.setattr(embedding_service.urllib.request, "urlopen", fake_urlopen)
    vec = embedding_service.embed_text("函数单调性")
    assert vec == [0.1, 0.2, 0.3]
    assert calls[0]["url"] == "https://embed.example.com/v1/embeddings"
    assert calls[0]["timeout"] == 60


def test_embed_api_missing_config_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "kb_embed_mode", "api")
    monkeypatch.setattr(settings, "embed_api_key", "")
    monkeypatch.setattr(settings, "embed_base_url", "")
    monkeypatch.setattr(settings, "embed_model", "")
    assert embedding_service.embed_text("函数单调性") is None


def test_embed_api_http_error_returns_none(monkeypatch):
    _set_api_config(monkeypatch)
    monkeypatch.setattr(settings, "embed_max_retries", 0)

    def fail_urlopen(req, timeout):
        raise TimeoutError("socket timeout")

    monkeypatch.setattr(embedding_service.urllib.request, "urlopen", fail_urlopen)
    assert embedding_service.embed_text("函数单调性") is None


def test_embed_off_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "kb_embed_mode", "off")
    assert embedding_service.embed_text("函数单调性") is None


def test_embed_empty_text_returns_none(monkeypatch):
    _set_api_config(monkeypatch)
    assert embedding_service.embed_text("   ") is None


# ---------------------------------------------------------------------------
# 合规双链路：知识库可出域，用户内容永不出域
# ---------------------------------------------------------------------------


def test_kb_source_may_use_offdomain_api(monkeypatch):
    """知识库内容走外部 API 是**既定决策**，不能被这次的修复误伤。"""
    _set_api_config(monkeypatch)
    calls: list[str] = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return _FakeUrlopen({"data": [{"embedding": [0.3, 0.2, 0.1]}]})

    monkeypatch.setattr(embedding_service.urllib.request, "urlopen", fake_urlopen)
    vec = embedding_service.embed_text("函数单调性", source=EMBED_SRC_KB)
    assert vec == [0.3, 0.2, 0.1]
    assert calls == ["https://embed.example.com/v1/embeddings"]


def test_user_source_never_calls_offdomain_api(monkeypatch):
    """🔴 KB_EMBED_MODE=api 时，用户内容也**不得**走外部 API。"""
    _set_api_config(monkeypatch)
    monkeypatch.setattr(
        embedding_service, "_embed_api",
        lambda text: pytest.fail("用户内容被发往外部 embedding API"),
    )
    # 本地模型没装 → _embed_local 抛错被吞 → 返回 None（宁缺毋滥、不造数）
    assert embedding_service.embed_text("错题原文", source=EMBED_SRC_USER) is None


def test_user_source_uses_local_even_when_api_configured(monkeypatch):
    """用户内容解析出的模式恒为 local，与 KB_EMBED_MODE 无关。"""
    for configured in ("api", "off", "cloud", "local"):
        monkeypatch.setattr(settings, "kb_embed_mode", configured)
        assert embedding_service.embed_mode_for(EMBED_SRC_USER) == "local"


def test_kb_source_follows_configured_mode(monkeypatch):
    """知识库链路仍按配置走，便于验证修复没有改变既定行为。"""
    for configured in ("api", "off", "local", "cloud"):
        monkeypatch.setattr(settings, "kb_embed_mode", configured)
        assert embedding_service.embed_mode_for(EMBED_SRC_KB) == configured


def test_offdomain_assert_blocks_user_source():
    assert_embed_source_offdomain_allowed(EMBED_SRC_KB)  # 放行
    with pytest.raises(EgressViolation):
        assert_embed_source_offdomain_allowed(EMBED_SRC_USER)


def test_offdomain_assert_blocks_undeclared_source():
    with pytest.raises(EgressViolation):
        assert_embed_source_offdomain_allowed("whatever")
    with pytest.raises(EgressViolation):
        assert_embed_source_offdomain_allowed("")


def test_unknown_source_falls_back_and_never_calls_api(monkeypatch):
    """来源没声明 → 判定不通过 → 退回本地，绝不放行到 api。"""
    _set_api_config(monkeypatch)
    monkeypatch.setattr(embedding_service, "_embed_local", lambda text: [0.5, 0.5])
    monkeypatch.setattr(
        embedding_service, "_embed_api",
        lambda text: pytest.fail("未声明来源被放行出域"),
    )
    assert embedding_service.embed_text("来路不明的文本", source="mystery") == [0.5, 0.5]

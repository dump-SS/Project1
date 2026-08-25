"""embedding_service 测试（S0-T7：第三方 API 分支 + 降级语义）。

覆盖：
- api 模式正常返回向量（mock HTTP 响应）
- api 模式配置缺失 → None（name_fuzzy 降级）
- api 模式 HTTP 异常 → None，不抛错
- off 模式 → None
"""
from __future__ import annotations

import json

import embedding_service
from config import settings


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

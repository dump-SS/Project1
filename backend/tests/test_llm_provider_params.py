"""LLM 生成参数配置化的回归测试（2026-10-18）。\n\n独立成文件是因为它盯的是 config/llm_provider 的**契约**：\n生成参数必须来自 settings，且默认值不得退回 1024。\n"""
from __future__ import annotations


# ---------- 生成参数配置化（2026-10-18，max_tokens 天花板） ----------


def test_generation_params_come_from_settings(monkeypatch):
    """🔴 llm_provider 不得再把 max_tokens / temperature 写成字面量。

    背景：原先硬编码 `max_tokens: 1024`，而生产模型GLM-5.3-Flash 是推理模型——
    带图时长prompt(1252 tok)+图 会让思维链把 1024 预算烧光（finish_reason='length'），
    content 返空串，上层回落成兜底话术「我暂时接不上你的话」。
    实测同一请求 max_tokens=4096 即正确返回。

    这条测试从**真正构造的 payload** 上断言，而不是断言源码里有某个字符串——
    源码断言挡不住「换个地方再硬编码一次」。
    """
    import json as _json

    import llm_provider
    from config import settings as s

    monkeypatch.setattr(s, "llm_api_key", "AK")
    monkeypatch.setattr(s, "llm_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(s, "llm_model", "fake-model")
    monkeypatch.setattr(s, "llm_max_tokens", 12345)
    monkeypatch.setattr(s, "llm_temperature", 0.77)

    seen: list[bytes] = []

    def fake_call_once(self, url, payload, headers):
        seen.append(payload)
        return "好的", {}

    monkeypatch.setattr(llm_provider.OpenAICompatibleProvider, "_call_once", fake_call_once)
    p = llm_provider.OpenAICompatibleProvider()
    p.generate("hi", context={"data_class": "state_plan"})

    assert seen, "generate 没真的发出请求"
    body = _json.loads(seen[0].decode("utf-8"))
    assert body["max_tokens"] == 12345, body
    assert body["temperature"] == 0.77, body


def test_default_max_tokens_is_4096():
    """默认值必须是 4096（实测带图+推理模型的够用预算），别被改回 1024。

    另外钉住「上限≠消耗」这个前提：它正是放宽该值不增加成本的理由。
    """
    from config import Settings

    s = Settings(_env_file=None)
    assert s.llm_max_tokens == 4096
    assert s.llm_temperature == 0.3

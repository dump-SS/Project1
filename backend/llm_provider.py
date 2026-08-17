"""LLM 供应商抽象（PRD 6.4：供应商抽象层，便于因合规/成本/稳定性切换）。

MVP 阶段默认用 MockProvider（返回 None），触发规则模板兜底——
这样不接真实 LLM 也能跑通整条建议/复盘链路。
等 config.llm_provider 改成真实供应商、填好 api_key 后，自动切换。
"""

from __future__ import annotations

import logging
from typing import Protocol

from config import settings

logger = logging.getLogger(__name__)

__all__ = ["LLMProvider", "get_provider", "MockProvider"]


class LLMProvider(Protocol):
    """供应商统一接口：给 prompt + 上下文，返回生成的文本或 None。"""

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        ...


class MockProvider:
    """默认供应商：永远返回 None，让 ai_suggestion 走规则模板兜底。

    用途：开发/测试阶段不依赖真实 LLM，验证整条链路（状态机、兜底、安全审核）。
    """

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        logger.info("[LLM] MockProvider 返回 None，将走规则兜底")
        return None


class OpenAICompatibleProvider:
    """兼容 OpenAI Chat Completions API 的供应商（如 OpenAI / 通义千问 / 智谱）。

    需要 config.py 里填好 llm_api_key / llm_base_url / llm_model。
    10s 超时（PRD 6.4），失败返回 None 让调用方走兜底。
    """

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise ValueError("OpenAICompatibleProvider 需要 llm_api_key")

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        import json
        import urllib.request
        import urllib.error

        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        # prompts/suggestion.txt 拆 SYSTEM / USER 两块；这里把它们分别放进 messages。
        # MockProvider 不需要 system；这样真实 LLM 也能拿到硬约束。
        messages = []
        system_prompt = (context or {}).get("system")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps({
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 800,
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }

        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = body["choices"][0]["message"]["content"]
                logger.info("[LLM] 生成成功，长度 %d", len(text))
                return text
        except Exception as e:
            logger.warning("[LLM] 生成失败: %s，将走兜底", e)
            return None


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """按 config.llm_provider 返回单例供应商。"""
    global _provider
    if _provider is not None:
        return _provider

    if settings.llm_provider == "mock" or not settings.llm_api_key:
        _provider = MockProvider()
    else:
        _provider = OpenAICompatibleProvider()
    return _provider

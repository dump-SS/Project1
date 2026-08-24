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
    """供应商统一接口：给 prompt + 上下文，返回生成的文本或 None。

    context 里可带 data_class（PRD 12.6）：provider 层对 knowledge_raw 二次兜底拒绝，
    防止业务代码绕过上层的 EgressGuard#check 直接调用。
    """

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        ...


def _enforce_egress(prompt: str, context: dict | None) -> None:
    """provider 层兜底：knowledge_raw 出域直接拒绝（多层防线，PRD 12.6）。"""
    data_class = (context or {}).get("data_class")
    if data_class is None:
        return  # 板块一历史调用未声明：默认按 state_plan 放行（向后兼容）
    from egress_guard import Guard, KNOWLEDGE_RAW

    if data_class == KNOWLEDGE_RAW:
        from egress_guard import EgressViolation

        raise EgressViolation("knowledge_raw 禁止出域（provider 层兜底拦截）")
    # 聚合包白名单校验：调用方传的出域 payload 以 context["egress_fields"] 声明
    fields = (context or {}).get("egress_fields")
    if fields is not None:
        Guard.check(fields, data_class)


class MockProvider:
    """默认供应商：永远返回 None，让 ai_suggestion 走规则模板兜底。

    用途：开发/测试阶段不依赖真实 LLM，验证整条链路（状态机、兜底、安全审核）。
    """

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        _enforce_egress(prompt, context)
        logger.info("[LLM] MockProvider 返回 None，将走规则兜底")
        return None


class OpenAICompatibleProvider:
    """兼容 OpenAI Chat Completions API 的供应商（如 OpenAI / 通义千问 / 智谱 / aiping.cn）。

    需要 config.py 里填好 llm_api_key / llm_base_url / llm_model。
    默认 30s 超时（PRD 6.4 上限可调到 60s），失败重试 1 次后返回 None 让调用方走兜底。
    """

    # PRD 6.4：超时上限与重试次数。示例值 10s 对慢供应商（如 aiping Step-3.5）
    # 实测响应 17-30s+ 波动，取 60s 上限；重试 1 次（共 2 次尝试）。
    # 注意：同步生成模式下最坏 POST 耗时 ~2min，这是 MVP 已知限制，
    # 异步化（BackgroundTasks/队列）后才符合 PRD 6.4"不阻塞主流程"。
    REQUEST_TIMEOUT = 60
    MAX_RETRIES = 1  # 共 2 次尝试：1 次原始 + 1 次重试

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise ValueError("OpenAICompatibleProvider 需要 llm_api_key")

    def _call_once(self, url: str, payload: bytes, headers: dict) -> str | None:
        """单次 HTTP 调用，任何失败都返回 None（绝不向上抛异常）。

        PRD 5.2/6.4：API 调用失败一律回退，异常穿透会导致路由 500。
        socket 读超时抛 TimeoutError（非 URLError 子类），此前漏捕导致
        重试逻辑失效、异常直接穿透——已改为捕 Exception 兜底。
        """
        import json
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — 供应商任何异常都必须降级为 None
            logger.warning("[LLM] 单次请求失败: %s: %s", type(e).__name__, e)
            return None

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        _enforce_egress(prompt, context)
        import json
        import time

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
            "temperature": 0.3,
            "max_tokens": 1024,
            # 关闭思维链：Doubao-Seed-2.0-mini 是推理模型，思维链会吃光 token 导致 content 为空
            "thinking": {"type": "disabled"},
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }

        # PRD 6.4：失败重试不超过 2 次（共 3 次尝试），避免长链路雪崩
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0:
                # 简单退避 1s
                time.sleep(1)
                logger.info("[LLM] 第 %d 次重试", attempt + 1)
            text = self._call_once(url, payload, headers)
            if text is not None:
                if attempt > 0:
                    logger.info("[LLM] 重试成功")
                else:
                    logger.info("[LLM] 生成成功，长度 %d", len(text))
                return text
        logger.warning("[LLM] 重试 %d 次后仍失败，将走兜底", self.MAX_RETRIES)
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

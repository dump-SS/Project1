"""embedding 服务封装（PRD 12.2.3 / ADR 选型：本地 bge-small-zh-v1.5，2026-08-25 起支持第三方 API）。

**合规双链路（AGENTS.md 铁律 6 / PRD 12.6，两条不许混）**：

- 知识库内容（编者提供、公开）→ ``source=EMBED_SRC_KB``，允许走外部 embedding API（既定决策）。
- 用户内容（错题原文 / 作答 / 学习记录）→ ``source=EMBED_SRC_USER``，**强制本地模型，永不出域**。
  这条不提供配置开关：``KB_EMBED_MODE=api`` 不会让用户内容跟着出域。
  本地模型不可用时**宁缺毋滥、不向量**（返回 ``None``，调用方降级 name_fuzzy），
  不用零向量或报错冒充——沿用 D34「转译不出就缺省、不造数」。

降级永远可用：

- embed_mode 由 config 控制：local / api / off（cloud 为历史占位，视为未知模式降级）
- 默认 off：不加载大模型、不发出域请求，知识点匹配走 name_fuzzy 降级
- local：延迟 import sentence-transformers（不装也能 import 本模块）
- api：OpenAI 兼容 /v1/embeddings（第三方 API，允许适当出域；自有服务器模型只需换
  embed_base_url/embed_model，接口形态一致——这是为日后接入自有模型预留的切换位）
- 任何异常都返回 None，调用方降级，不把错误抛到路由层
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from config import settings
from egress_guard import (
    EMBED_SRC_KB,
    EMBED_SRC_USER,
    EgressViolation,
    assert_embed_source_offdomain_allowed,
)

logger = logging.getLogger(__name__)

__all__ = [
    "embed_text",
    "embed_mode",
    "embed_mode_for",
    "MODEL_NAME",
    "EMBED_DIM",
    "EMBED_SRC_KB",
    "EMBED_SRC_USER",
]

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBED_DIM = 512  # bge-small-zh-v1.5 默认输出维度（仅 local 模式使用；api 模式以返回长度为准）


def embed_mode() -> str:
    """当前 embedding 模式，来自 settings（默认 off）。知识库链路用这个。"""
    return getattr(settings, "kb_embed_mode", "off")


def embed_mode_for(source: str) -> str:
    """给定数据来源，实际生效的 embedding 模式。

    用户内容**永远**是 local——不看 ``KB_EMBED_MODE``。配置成 api/off 时这里返回
    ``local``，调用方据此判断「本条到底会不会走向量」，并把**实际使用的模式**写进
    ``kb_embeddings.model``（别把全局配置值当成实际模式记，那会记错）。
    """
    if source == EMBED_SRC_USER:
        return "local"
    return embed_mode()


_model = None

# 「用户内容不随配置出域」这条提示按进程去重：live 配置常驻 KB_EMBED_MODE=api，
# 不去重的话每条错题都会重复刷同一句。
_warned_user_scope: set[str] = set()


def _get_model():
    global _model
    if _model is not None:
        return _model
    import sentence_transformers  # 延迟加载，非 local 模式绝不 import

    _model = sentence_transformers.SentenceTransformer(MODEL_NAME)
    logger.info("[EMBED] local model loaded: %s", MODEL_NAME)
    return _model


def _embed_local(text: str) -> list[float] | None:
    """本地 bge 模型向量化。模型未装/加载失败返回 None。"""
    model = _get_model()
    vec = model.encode([text], normalize_embeddings=True)[0]
    return vec.tolist()


def _embed_api(text: str) -> list[float] | None:
    """OpenAI 兼容 /v1/embeddings 向量化（第三方 API / 自有服务器）。

    配置缺失、超时、非 200、响应结构非法一律返回 None 走 name_fuzzy 降级。
    """
    if not settings.embed_api_key or not settings.embed_base_url or not settings.embed_model:
        logger.warning("[EMBED] api 模式配置缺失（embed_api_key/base_url/model），降级 name_fuzzy")
        return None
    url = f"{settings.embed_base_url.rstrip('/')}/embeddings"
    payload = json.dumps({"model": settings.embed_model, "input": text}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.embed_api_key}",
    }
    attempts = settings.embed_max_retries + 1
    for attempt in range(attempts):
        if attempt > 0:
            time.sleep(1)
            logger.info("[EMBED] 第 %d 次重试", attempt + 1)
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=settings.embed_request_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            vec = body["data"][0]["embedding"]
            if not vec:
                raise ValueError("embedding 为空")
            return [float(v) for v in vec]
        except Exception as e:  # noqa: BLE001 — 供应商任何异常都必须降级为 None
            logger.warning("[EMBED] api 请求失败（第 %d 次）: %s: %s", attempt + 1, type(e).__name__, e)
    return None


def embed_text(text: str, *, source: str = EMBED_SRC_KB) -> list[float] | None:
    """文本 → 向量。失败/模式 off 返回 None（调用方降级）。

    Args:
        text: 待向量化文本。
        source: 数据来源。``EMBED_SRC_KB``=知识库内容（允许出域）；
            ``EMBED_SRC_USER``=用户内容（错题原文/作答/学习记录），
            **强制本地模型、永不出域**。
            传用户内容时必须显式传 ``EMBED_SRC_USER``——缺省会按知识库处理并可能出域。

    用户内容走 local 而 local 不可用时返回 None——**宁缺毋滥、不造数**（D34）。
    """
    mode = embed_mode_for(source)

    if source == EMBED_SRC_USER and embed_mode() == "api" and "user" not in _warned_user_scope:
        _warned_user_scope.add("user")
        logger.warning(
            "[EMBED] 用户内容（错题/学习记录）不随 KB_EMBED_MODE 出域，本条强制走本地模型"
        )

    if mode == "off":
        return None
    if not text or not text.strip():
        return None

    if mode == "api":
        try:
            assert_embed_source_offdomain_allowed(source)
        except EgressViolation:
            # 兜底：source 与 mode 组合非法（例如有人给用户内容硬塞了 api 模式）时
            # 绝不放行，退回 local；local 再失败就返回 None。
            logger.error("[EMBED] 出域判定未通过，退回本地模型")
            mode = "local"

    try:
        if mode == "api":
            return _embed_api(text.strip())
        if mode == "local":
            return _embed_local(text.strip())
        # cloud 等未接入模式：记录并降级（历史占位，语义保留）
        logger.warning("[EMBED] 模式 %s 未接入，暂降级 name_fuzzy", mode)
        return None
    except Exception:  # noqa: BLE001 — 模型未装/加载失败均降级
        logger.exception("[EMBED] embedding 失败，降级 name_fuzzy")
        return None

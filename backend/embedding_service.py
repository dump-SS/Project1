"""embedding 服务封装（PRD 12.2.3 / ADR 选型：本地 bge-small-zh-v1.5，2026-08-25 起支持第三方 API）。

关键设计（降级永远可用）：
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

logger = logging.getLogger(__name__)

__all__ = ["embed_text", "embed_mode", "MODEL_NAME", "EMBED_DIM"]

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBED_DIM = 512  # bge-small-zh-v1.5 默认输出维度（仅 local 模式使用；api 模式以返回长度为准）


def embed_mode() -> str:
    """当前 embedding 模式，来自 settings（默认 off）。"""
    return getattr(settings, "kb_embed_mode", "off")


_model = None


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


def embed_text(text: str) -> list[float] | None:
    """文本 → 向量。失败/模式 off 返回 None（调用方降级）。"""
    mode = embed_mode()
    if mode == "off":
        return None
    if not text or not text.strip():
        return None
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

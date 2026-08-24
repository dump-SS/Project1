"""本地 embedding 服务封装（PRD 12.2.3 / ADR 选型：bge-small-zh-v1.5）。

关键设计（降级永远可用）：
- embed_mode 由 config 控制：local / cloud / off
- 默认 off：不加载大模型，知识点匹配走 name_fuzzy 降级
- local：延迟 import sentence-transformers（不装也能 import 本模块）
- 任何异常都返回 None，调用方降级，不把错误抛到路由层
"""
from __future__ import annotations

import logging

from config import settings

logger = logging.getLogger(__name__)

__all__ = ["embed_text", "embed_mode", "MODEL_NAME", "EMBED_DIM"]

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBED_DIM = 512  # bge-small-zh-v1.5 默认输出维度


def embed_mode() -> str:
    """当前 embedding 模式，来自 settings（默认 off）。"""
    return getattr(settings, "kb_embed_mode", "off")


_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    import sentence_transformers  # 延迟加载，off 模式绝不 import

    _model = sentence_transformers.SentenceTransformer(MODEL_NAME)
    logger.info("[EMBED] local model loaded: %s", MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float] | None:
    """文本 → 向量。失败/模式 off 返回 None（调用方降级）。"""
    mode = embed_mode()
    if mode == "off":
        return None
    try:
        if mode != "local":
            # cloud 过渡开关：不实现真实云端调用，返回 None 走降级
            logger.warning("[EMBED] cloud 模式未接入，暂降级 name_fuzzy")
            return None
        if not text or not text.strip():
            return None
        model = _get_model()
        vec = model.encode([text], normalize_embeddings=True)[0]
        return vec.tolist()
    except Exception:  # noqa: BLE001 — 模型未装/加载失败均降级
        logger.exception("[EMBED] embedding 失败，降级 name_fuzzy")
        return None

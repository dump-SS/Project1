"""本地向量库封装（ADR 选型：FAISS）。

MVP 降级策略（PRD 12.11 / 计划书 §3.3）：
- FAISS 依赖缺失或索引不可用时，search 返回 []，由调用方走 name_fuzzy 降级；
- 索引文件与 SQLite 同目录（满足 PRD 12.2.3 可备份/销毁），按需懒加载；
- 本次 v2.1 默认 embed_mode=off，本模块仅提供接口形态，
  真实 FAISS 索引在 embedding 模型就绪（v2.1-B4）后启用。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

__all__ = ["add", "search", "VECTOR_INDEX_DIR"]


def _index_root() -> Path:
    """索引目录：与 SQLite 同目录的 kb_vectors/。"""
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        raw = db_url[len("sqlite:///"):]
        db_path = Path(raw)
        if not db_path.is_absolute():
            db_path = Path.cwd() / raw
        return db_path.parent / "kb_vectors"
    return Path.cwd() / "kb_vectors"


VECTOR_INDEX_DIR = _index_root()


def search(vector: list[float], top_k: int = 5, subject: str | None = None) -> list[tuple[str, float]]:
    """按向量检索 Top-K，返回 [(ref_id, similarity)]。不可用时返回空列表。"""
    try:
        import faiss  # noqa: F401  延迟 import，未装不阻塞
        import numpy as np
    except Exception:  # noqa: BLE001
        logger.info("[VECTOR] FAISS 未安装，search 降级为空")
        return []
    # v2.1 阶段：索引未初始化（embed off），返回空；调用方 name_fuzzy 兜底。
    return []


def add(vector: list[float], vector_id: str, ref_type: str, ref_id: str, model: str, dim: int) -> bool:
    """写入向量索引。失败返回 False（写入 kb_embeddings 引用可继续）。"""
    try:
        import faiss  # noqa: F401
        import numpy as np
    except Exception:  # noqa: BLE001
        logger.info("[VECTOR] FAISS 未安装，add 跳过")
        return False
    # v2.1：embed off，不维护索引；表引用由错误本 API 单独写 kb_embeddings。
    return False

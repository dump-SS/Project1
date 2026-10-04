"""本地向量库封装（ADR 选型：FAISS）。

策略（PRD 12.11 / 计划书 §3.3）：
- FAISS 依赖缺失或索引不可用时，search 返回 []，由调用方走 name_fuzzy 降级；
- 索引文件与 SQLite 同目录（满足 PRD 12.2.3 可备份/销毁），首次调用懒加载，
  每次 add 后落盘（MVP 规模小，全量写可接受）；
- 向量本体只存本地（kb_embeddings 表仅存引用），因此索引必须落盘持久化——
  无磁盘文件时无法从引用表重建向量（引用表不含向量本体）。

S0-T7b（2026-08-25）实装：IndexFlatIP + L2 归一化（内积=余弦），
add/search/rebuild 全链路。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "add",
    "search",
    "rebuild_index",
    "VECTOR_INDEX_DIR",
    "index_stats",
    "vector_index_status",
]


def _index_source() -> str:
    """索引目录的来源标识（KB_VECTOR_DIR / sqlite / cwd），供诊断暴露。"""
    if (settings.kb_vector_dir or "").strip():
        return "kb_vector_dir"
    return "sqlite" if settings.database_url.startswith("sqlite:///") else "cwd"


def _index_root() -> Path:
    """索引目录解析优先级：``KB_VECTOR_DIR`` > SQLite 同目录 > ``cwd/kb_vectors``。

    为什么需要 ``KB_VECTOR_DIR``：生产 ``DATABASE_URL`` 是 Neon（非 SQLite），
    旧逻辑静默 ``return Path.cwd() / "kb_vectors"``——索引路径变成**进程工作目录**，
    容器里每次重启都可能是新路径，于是冷启动读不到索引、检索静悄悄降级成
    ``name_fuzzy``，而日志与响应里都看不出任何异常。

    刻意**不抛错**：索引不可用时 search 返回 []、调用方走 name_fuzzy 是ADR 早已
    定好的降级路径；pilot 期「服务起不来」比「检索降级」更糟。异常一律改为
    error 级日志 + 只读接口暴露（见 :func:`vector_index_status`）。
    """
    configured = (settings.kb_vector_dir or "").strip()
    if configured:
        root = Path(configured)
        logger.info("[VECTOR] 索引目录来自 KB_VECTOR_DIR=%s", root)
        return root

    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        raw = db_url[len("sqlite:///"):]
        db_path = Path(raw)
        if not db_path.is_absolute():
            db_path = Path.cwd() / raw
        root = db_path.parent / "kb_vectors"
        logger.info("[VECTOR] 索引目录来自 SQLite 同目录=%s", root)
        return root

    root = Path.cwd() / "kb_vectors"
    logger.warning(
        "[VECTOR] 索引目录回落到 cwd=%s：DATABASE_URL 非 SQLite 且未设 KB_VECTOR_DIR。"
        "容器每次重启工作目录可能不同 → 可能读不到索引并静默降级 name_fuzzy。"
        "请设 KB_VECTOR_DIR 指向索引目录。",
        root,
    )
    return root


VECTOR_INDEX_DIR = _index_root()

_INDEX_FILE = VECTOR_INDEX_DIR / "embeddings.index"
_REFS_FILE = VECTOR_INDEX_DIR / "refs.json"

_lock = threading.Lock()

# 进程内状态：索引 + 有序引用列表（与索引行号一一对应）
_index = None
_refs: list[dict] = []  # [{"vectorId", "refId", "refType", "model"}]


def _index_problems(total: int | None, refs_n: int) -> list[str]:
    """列出索引的全部异常，**每条都带实际值**（空列表 = 健康）。

    只诊断不修复、不抛错。条目数与基准不符时提示先查同步性而非直接重建——
    refs.json 与库不同步时重建索引会把正确的向量覆盖成错的。
    """
    problems: list[str] = []
    expected = settings.kb_vector_expected_count

    if not VECTOR_INDEX_DIR.exists():
        problems.append(f"索引目录不存在：{VECTOR_INDEX_DIR}")
    if not _INDEX_FILE.exists():
        problems.append(f"索引文件缺失：{_INDEX_FILE}（{_INDEX_FILE.stat().st_size if _INDEX_FILE.exists() else 0} bytes）")
    if not _REFS_FILE.exists():
        problems.append(f"引用文件缺失：{_REFS_FILE}")

    if total is None:
        problems.append("索引未加载（_index is None），search 将降级 name_fuzzy")
        return problems

    if total != expected:
        problems.append(
            f"索引条目数 {total} != 基准 {expected}"
            f"（先核对 refs.json 与库表是否同步，不要直接重建索引）"
        )
    if total != refs_n:
        problems.append(f"refs.json 条目数 {refs_n} != 索引行数 {total}（两者必须一一对应）")
    return problems


def _log_index_problems(total: int | None, dim: int | None, refs_n: int) -> None:
    """把索引异常打成 error 且带实际值；正常时打 info 便于确认加载结果。"""
    problems = _index_problems(total, refs_n)
    if not problems:
        logger.info(
            "[VECTOR] 索引自检通过：%d 条 / dim=%s（基准 %d）@ %s",
            total, dim, settings.kb_vector_expected_count, _INDEX_FILE,
        )
        return
    for problem in problems:
        logger.error("[VECTOR] 索引异常：%s", problem)


def _import_faiss():
    try:
        import faiss
        import numpy as np
        return faiss, np
    except Exception:  # noqa: BLE001
        return None, None


def _load_from_disk() -> None:
    """懒加载：磁盘有索引则加载，否则保持空索引（等待首次 add 建库）。

    加载后立即自检并把异常打成 error（带实际值）——**不抛错**：降级是既定行为。
    """
    global _index, _refs
    if _index is not None:
        return
    faiss, np = _import_faiss()
    if faiss is None:
        logger.info("[VECTOR] FAISS 未安装，search 降级为空")
        return
    _refs = []
    if _INDEX_FILE.exists():
        try:
            _index = faiss.read_index(str(_INDEX_FILE))
            if _REFS_FILE.exists():
                _refs = json.loads(_REFS_FILE.read_text(encoding="utf-8"))
            logger.info("[VECTOR] 已加载索引：%d 条，dim=%d", _index.ntotal, _index.d)
        except Exception:  # noqa: BLE001 — 索引文件损坏时重建空索引
            logger.exception("[VECTOR] 索引文件损坏，重建空索引")
            _index = None
            _refs = []
    else:
        logger.error(
            "[VECTOR] 索引文件不存在：%s（目录是否存在：%s）→ 检索将降级 name_fuzzy",
            _INDEX_FILE, VECTOR_INDEX_DIR.exists(),
        )
    if _index is None:
        _index = None  # 等首次 add 时按向量维度建库
        return
    _log_index_problems(_index.ntotal, _index.d, len(_refs))
    return


def _persist() -> None:
    """落盘索引与引用表（add 后调用；MVP 全量写）。"""
    import faiss

    _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(_index, str(_INDEX_FILE))
    _REFS_FILE.write_text(json.dumps(_refs, ensure_ascii=False), encoding="utf-8")


def _normalize(vec, np) -> list[float]:
    """L2 归一化：IndexFlatIP 内积 = 余弦相似度，与 normalize_embeddings=True 口径一致。"""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return list(vec)
    return (vec / norm).tolist()


def add(vector: list[float], vector_id: str, ref_type: str, ref_id: str, model: str, dim: int) -> bool:
    """写入向量索引（L2 归一化后入 IndexFlatIP）并落盘。失败返回 False（引用仍可继续写表）。"""
    global _index, _refs
    with _lock:
        faiss, np = _import_faiss()
        if faiss is None:
            logger.info("[VECTOR] FAISS 未安装，add 跳过")
            return False
        try:
            _load_from_disk()
            arr = np.asarray(vector, dtype="float32").reshape(1, -1)
            if _index is None:
                if dim <= 0 or arr.shape[1] != dim:
                    dim = arr.shape[1]
                _index = faiss.IndexFlatIP(dim)
            if arr.shape[1] != _index.d:
                logger.warning(
                    "[VECTOR] 维度不一致（索引 %d / 向量 %d），跳过 %s",
                    _index.d, arr.shape[1], vector_id,
                )
                return False
            _index.add(np.asarray(_normalize(arr[0], np), dtype="float32").reshape(1, -1))
            _refs.append({"vectorId": vector_id, "refId": ref_id, "refType": ref_type, "model": model})
            _persist()
            return True
        except Exception:  # noqa: BLE001 — 索引写入失败不阻断业务
            logger.exception("[VECTOR] add 失败，跳过 %s", vector_id)
            return False


def search(vector: list[float], top_k: int = 5, subject: str | None = None) -> list[tuple[str, float]]:
    """按向量检索 Top-K，返回 [(ref_id, similarity)]。不可用时返回空列表。

    subject 参数由调用方按 ref 的学科过滤（本索引不存学科），MVP 保持忽略。
    """
    global _index, _refs
    with _lock:
        faiss, np = _import_faiss()
        if faiss is None:
            logger.info("[VECTOR] FAISS 未安装，search 降级为空")
            return []
        try:
            _load_from_disk()
            if _index is None or _index.ntotal == 0:
                return []
            q = np.asarray(vector, dtype="float32").reshape(1, -1)
            if q.shape[1] != _index.d:
                logger.warning("[VECTOR] 查询维度 %d 与索引 %d 不一致", q.shape[1], _index.d)
                return []
            q = np.asarray(_normalize(q[0], np), dtype="float32").reshape(1, -1)
            k = min(top_k, _index.ntotal)
            scores, ids = _index.search(q, k)
            out = []
            for score, idx in zip(scores[0], ids[0]):
                if idx < 0 or idx >= len(_refs):
                    continue
                out.append((_refs[int(idx)]["refId"], round(float(score), 4)))
            return out
        except Exception:  # noqa: BLE001
            logger.exception("[VECTOR] search 失败，降级为空")
            return []


def rebuild_index() -> bool:
    """清空并重建索引（删除磁盘文件）。

    用于：模型/维度切换后废弃旧向量、或人工修复索引损坏。
    注意 kb_embeddings 引用表不含向量本体，重建后需重新向量化入库。
    """
    global _index, _refs
    with _lock:
        _index = None
        _refs = []
        try:
            if _INDEX_FILE.exists():
                _INDEX_FILE.unlink()
            if _REFS_FILE.exists():
                _REFS_FILE.unlink()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("[VECTOR] rebuild 失败")
            return False


def index_stats() -> dict:
    """索引状态（诊断用）。"""
    global _index, _refs
    with _lock:
        try:
            _load_from_disk()
        except Exception:  # noqa: BLE001
            pass
        return {
            "total": _index.ntotal if _index is not None else 0,
            "dim": _index.d if _index is not None else None,
            "refs": len(_refs),
            "indexFile": str(_INDEX_FILE),
        }


def vector_index_status() -> dict:
    """向量索引完整状态（只读诊断，不改任何状态）。

    存在的理由：索引读不到时应用**照常启动**、检索静悄悄降级 name_fuzzy ——
    只打日志不够（没人盯日志流就等于没写），所以把状态暴露到只读接口，
    让「静默降级」变成「可观测」。部署检查清单与监控都读这个口径。
    """
    global _index, _refs
    with _lock:
        try:
            _load_from_disk()
        except Exception:  # noqa: BLE001 — 状态接口不该因索引异常而失败
            logger.exception("[VECTOR] 读取索引状态时异常")

        total = _index.ntotal if _index is not None else None
        dim = _index.d if _index is not None else None
        refs_n = len(_refs)
        problems = _index_problems(total, refs_n)
        expected = settings.kb_vector_expected_count

        return {
            "status": "ok" if not problems else "degraded",
            # False = 检索会降级 name_fuzzy（功能可用、匹配质量下降）
            "searchable": bool(total),
            "searchMode": "vector" if total else "name_fuzzy",
            "count": total,
            "expectedCount": expected,
            "dim": dim,
            "refs": refs_n,
            "indexDir": str(VECTOR_INDEX_DIR),
            "indexDirSource": _index_source(),
            "indexFile": str(_INDEX_FILE),
            "refsFile": str(_REFS_FILE),
            "indexFileExists": _INDEX_FILE.exists(),
            "refsFileExists": _REFS_FILE.exists(),
            "embedMode": settings.kb_embed_mode,
            "problems": problems,
        }

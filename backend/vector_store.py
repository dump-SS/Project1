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
    "STORE_KB",
    "STORE_USER",
]


# --- 向量库命名空间（物理隔离）------------------------------------------------
#
# 为什么需要它（2026-10-06，开关冲突案 · 方案 B）：
# 知识库向量（3391 条）是**从 R2 下载的共享只读产物**，`add()` 会落盘改写同一个
# `embeddings.index` → 用户内容一旦写进来，就会污染生产检索，且索引自检
# （实际条数 != KB_VECTOR_EXPECTED_COUNT）会每次启动报 error。
#
# 隔离手段：**用户内容写独立目录，物理上不碰 KB 索引文件**。
#   - KB 侧：<VECTOR_INDEX_DIR>/embeddings.index      （路径与既有行为完全一致）
#   - 用户侧：<VECTOR_INDEX_DIR>/user/embeddings.index（独立文件、独立 refs.json）
#
# 这是「真隔离」而不是改个变量名：两者是**不同的磁盘文件**，
# 用户内容的 add() 不可能改到 KB 的 embeddings.index 的任何一个字节。
STORE_KB = "kb"
STORE_USER = "user"

# 允许的命名空间 → 子目录名（kb 为空 = 沿用根目录，保证既有路径不变）
_STORE_SUBDIRS: dict[str, str] = {STORE_KB: "", STORE_USER: "user"}


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


def _store_dir(store: str) -> Path:
    """命名空间对应的索引目录。``kb`` 沿用根目录（既有路径零变化），其余进子目录。"""
    sub = _STORE_SUBDIRS.get(store)
    if sub is None:
        raise ValueError(f"未知的向量库命名空间：{store!r}（可选 {sorted(_STORE_SUBDIRS)}）")
    return VECTOR_INDEX_DIR / sub if sub else VECTOR_INDEX_DIR


def _index_file(store: str) -> Path:
    return _store_dir(store) / "embeddings.index"


def _refs_file(store: str) -> Path:
    return _store_dir(store) / "refs.json"


_lock = threading.Lock()

# 进程内状态按命名空间分桶：每个 store 各有独立的索引 + 有序引用列表。
# 这样 KB 与用户内容的加载/落盘互不干扰，`_refs` 也不会串行号。
_indexes: dict[str, object | None] = {}
_refs_by_store: dict[str, list[dict]] = {}


def _refs_of(store: str) -> list[dict]:
    """取该命名空间的引用列表（惰性建空表）。"""
    return _refs_by_store.setdefault(store, [])


def _index_problems(store: str, total: int | None, refs_n: int) -> list[str]:
    """列出索引的全部异常，**每条都带实际值**（空列表 = 健康）。

    只诊断不修复、不抛错。条目数与基准不符时提示先查同步性而非直接重建——
    refs.json 与库不同步时重建索引会把正确的向量覆盖成错的。

    KB 命名空间的条目数基准是 ``KB_VECTOR_EXPECTED_COUNT``（生产共享产物的条数）；
    **用户命名空间不适用该基准**（条数随用户内容增长），故只在 KB 侧比对。
    """
    problems: list[str] = []
    index_file = _index_file(store)
    refs_file = _refs_file(store)
    store_dir = _store_dir(store)

    if not store_dir.exists():
        problems.append(f"索引目录不存在：{store_dir}")
    if not index_file.exists():
        problems.append(f"索引文件缺失：{index_file}（{index_file.stat().st_size if index_file.exists() else 0} bytes）")
    if not refs_file.exists():
        problems.append(f"引用文件缺失：{refs_file}")

    if total is None:
        problems.append("索引未加载（_index is None），search 将降级 name_fuzzy")
        return problems

    expected = settings.kb_vector_expected_count
    if store == STORE_KB and total != expected:
        problems.append(
            f"索引条目数 {total} != 基准 {expected}"
            f"（先核对 refs.json 与库表是否同步，不要直接重建索引）"
        )
    if total != refs_n:
        problems.append(f"refs.json 条目数 {refs_n} != 索引行数 {total}（两者必须一一对应）")
    return problems


def _log_index_problems(store: str, total: int | None, dim: int | None, refs_n: int) -> None:
    """把索引异常打成 error 且带实际值；正常时打 info 便于确认加载结果。"""
    problems = _index_problems(store, total, refs_n)
    if not problems:
        logger.info(
            "[VECTOR] 索引自检通过（store=%s）：%d 条 / dim=%s（基准 %d）@ %s",
            store, total, dim, settings.kb_vector_expected_count, _index_file(store),
        )
        return
    for problem in problems:
        logger.error("[VECTOR] 索引异常（store=%s）：%s", store, problem)


def _import_faiss():
    try:
        import faiss
        import numpy as np
        return faiss, np
    except Exception:  # noqa: BLE001
        return None, None


def _load_from_disk(store: str) -> None:
    """懒加载：磁盘有索引则加载，否则保持空索引（等待首次 add 建库）。

    加载后立即自检并把异常打成 error（带实际值）——**不抛错**：降级是既定行为。
    """
    if _indexes.get(store) is not None:
        return
    faiss, np = _import_faiss()
    if faiss is None:
        logger.info("[VECTOR] FAISS 未安装，search 降级为空")
        return
    index_file = _index_file(store)
    refs_file = _refs_file(store)
    refs: list[dict] = []
    index = None
    if index_file.exists():
        try:
            index = faiss.read_index(str(index_file))
            if refs_file.exists():
                refs = json.loads(refs_file.read_text(encoding="utf-8"))
            logger.info("[VECTOR] 已加载索引（store=%s）：%d 条，dim=%d", store, index.ntotal, index.d)
        except Exception:  # noqa: BLE001 — 索引文件损坏时重建空索引
            logger.exception("[VECTOR] 索引文件损坏，重建空索引（store=%s）", store)
            index = None
            refs = []
    else:
        logger.error(
            "[VECTOR] 索引文件不存在：%s（目录是否存在：%s）→ 检索将降级 name_fuzzy",
            index_file, _store_dir(store).exists(),
        )
    _indexes[store] = index
    _refs_by_store[store] = refs
    if index is None:
        return
    _log_index_problems(store, index.ntotal, index.d, len(refs))
    return


def _persist(store: str) -> None:
    """落盘索引与引用表（add 后调用；MVP 全量写）。"""
    import faiss

    index_file = _index_file(store)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(_indexes[store], str(index_file))
    _refs_file(store).write_text(
        json.dumps(_refs_of(store), ensure_ascii=False), encoding="utf-8"
    )


def _normalize(vec, np) -> list[float]:
    """L2 归一化：IndexFlatIP 内积 = 余弦相似度，与 normalize_embeddings=True 口径一致。"""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return list(vec)
    return (vec / norm).tolist()


def add(
    vector: list[float],
    vector_id: str,
    ref_type: str,
    ref_id: str,
    model: str,
    dim: int,
    *,
    store: str = STORE_KB,
) -> bool:
    """写入向量索引（L2 归一化后入 IndexFlatIP）并落盘。失败返回 False（引用仍可继续写表）。

    Args:
        store: 命名空间。``STORE_KB``（默认）= 知识库共享索引；``STORE_USER`` = 用户内容独立索引。
            **用户内容（错题/学习记录）必须传 ``store=STORE_USER``** —— 否则会写进 KB 的
            生产索引，污染检索并让索引自检持续报错（见模块顶部说明）。
    """
    with _lock:
        faiss, np = _import_faiss()
        if faiss is None:
            logger.info("[VECTOR] FAISS 未安装，add 跳过")
            return False
        try:
            _load_from_disk(store)
            index = _indexes.get(store)
            arr = np.asarray(vector, dtype="float32").reshape(1, -1)
            if index is None:
                if dim <= 0 or arr.shape[1] != dim:
                    dim = arr.shape[1]
                index = faiss.IndexFlatIP(dim)
                _indexes[store] = index
            if arr.shape[1] != index.d:
                logger.warning(
                    "[VECTOR] 维度不一致（索引 %d / 向量 %d），跳过 %s",
                    index.d, arr.shape[1], vector_id,
                )
                return False
            index.add(np.asarray(_normalize(arr[0], np), dtype="float32").reshape(1, -1))
            _refs_of(store).append(
                {"vectorId": vector_id, "refId": ref_id, "refType": ref_type, "model": model}
            )
            _persist(store)
            return True
        except Exception:  # noqa: BLE001 — 索引写入失败不阻断业务
            logger.exception("[VECTOR] add 失败，跳过 %s", vector_id)
            return False


def search(
    vector: list[float],
    top_k: int = 5,
    subject: str | None = None,
    *,
    store: str = STORE_KB,
) -> list[tuple[str, float]]:
    """按向量检索 Top-K，返回 [(ref_id, similarity)]。不可用时返回空列表。

    subject 参数由调用方按 ref 的学科过滤（本索引不存学科），MVP 保持忽略。
    store：命名空间，默认 KB；用户内容检索要显式传 ``STORE_USER``（与写入侧一致）。
    """
    with _lock:
        faiss, np = _import_faiss()
        if faiss is None:
            logger.info("[VECTOR] FAISS 未安装，search 降级为空")
            return []
        try:
            _load_from_disk(store)
            index = _indexes.get(store)
            refs = _refs_of(store)
            if index is None or index.ntotal == 0:
                return []
            q = np.asarray(vector, dtype="float32").reshape(1, -1)
            if q.shape[1] != index.d:
                logger.warning("[VECTOR] 查询维度 %d 与索引 %d 不一致", q.shape[1], index.d)
                return []
            q = np.asarray(_normalize(q[0], np), dtype="float32").reshape(1, -1)
            k = min(top_k, index.ntotal)
            scores, ids = index.search(q, k)
            out = []
            for score, idx in zip(scores[0], ids[0]):
                if idx < 0 or idx >= len(refs):
                    continue
                out.append((refs[int(idx)]["refId"], round(float(score), 4)))
            return out
        except Exception:  # noqa: BLE001
            logger.exception("[VECTOR] search 失败，降级为空")
            return []


def rebuild_index(*, store: str = STORE_KB) -> bool:
    """清空并重建索引（删除磁盘文件）。

    用于：模型/维度切换后废弃旧向量、或人工修复索引损坏。
    注意 kb_embeddings 引用表不含向量本体，重建后需重新向量化入库。
    store：命名空间，默认 KB（既有调用行为不变）。
    """
    with _lock:
        _indexes[store] = None
        _refs_by_store[store] = []
        index_file = _index_file(store)
        refs_file = _refs_file(store)
        try:
            if index_file.exists():
                index_file.unlink()
            if refs_file.exists():
                refs_file.unlink()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("[VECTOR] rebuild 失败（store=%s）", store)
            return False


def index_stats(*, store: str = STORE_KB) -> dict:
    """索引状态（诊断用）。store：命名空间，默认 KB。"""
    with _lock:
        try:
            _load_from_disk(store)
        except Exception:  # noqa: BLE001
            pass
        index = _indexes.get(store)
        return {
            "total": index.ntotal if index is not None else 0,
            "dim": index.d if index is not None else None,
            "refs": len(_refs_of(store)),
            "indexFile": str(_index_file(store)),
        }


def vector_index_status() -> dict:
    """向量索引完整状态（只读诊断，不改任何状态）。

    存在的理由：索引读不到时应用**照常启动**、检索静悄悄降级 name_fuzzy ——
    只打日志不够（没人盯日志流就等于没写），所以把状态暴露到只读接口，
    让「静默降级」变成「可观测」。部署检查清单与监控都读这个口径。

    **本接口只报 KB（知识库）索引**：它是生产共享产物、有条数基准、是部署检查的对象。
    用户内容索引随用户行为增长、无固定基准，其状态单独在 ``userStore`` 字段给出
    （仅供诊断，不参与 status/searchMode 判定）。
    """
    with _lock:
        try:
            _load_from_disk(STORE_KB)
        except Exception:  # noqa: BLE001 — 状态接口不该因索引异常而失败
            logger.exception("[VECTOR] 读取索引状态时异常")
        try:
            _load_from_disk(STORE_USER)
        except Exception:  # noqa: BLE001
            logger.exception("[VECTOR] 读取用户索引状态时异常")

        index = _indexes.get(STORE_KB)
        refs = _refs_of(STORE_KB)
        total = index.ntotal if index is not None else None
        dim = index.d if index is not None else None
        refs_n = len(refs)
        problems = _index_problems(STORE_KB, total, refs_n)
        expected = settings.kb_vector_expected_count

        user_index = _indexes.get(STORE_USER)
        user_total = user_index.ntotal if user_index is not None else 0

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
            "indexFile": str(_index_file(STORE_KB)),
            "refsFile": str(_refs_file(STORE_KB)),
            "indexFileExists": _index_file(STORE_KB).exists(),
            "refsFileExists": _refs_file(STORE_KB).exists(),
            "embedMode": settings.kb_embed_mode,
            # 用户内容索引（独立物理文件，诊断用；条数不参与上面的 status 判定）
            "userStore": {
                "count": user_total,
                "dim": user_index.d if user_index is not None else None,
                "indexDir": str(_store_dir(STORE_USER)),
                "indexFile": str(_index_file(STORE_USER)),
                "indexFileExists": _index_file(STORE_USER).exists(),
            },
            "problems": problems,
        }

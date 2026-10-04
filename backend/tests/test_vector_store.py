"""vector_store FAISS 实装测试（S0-T7b）。

覆盖：
- add → search 命中 Top-K 且相似度递减
- 空索引 search 返回 []
- 维度不一致 add 被跳过
- rebuild 清空索引

2026-10-04 新增（向量索引可观测性）：
- _index_root() 优先读 KB_VECTOR_DIR（生产 DATABASE_URL 是 Neon，非 SQLite）
- vector_index_status() 把静默降级变成可观测，且**不抛错**（pilot 期服务
  不可用比检索降级更糟）
"""
from __future__ import annotations

import importlib
import logging

import pytest

import vector_store

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("faiss"),
    reason="faiss-cpu 未安装",
)


@pytest.fixture(autouse=True)
def _clean_index():
    vector_store.rebuild_index()
    yield
    vector_store.rebuild_index()


def test_add_then_search_hits_topk():
    # 三个正交向量：查询 [1,0,0] 应最接近 v1
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    v3 = [0.0, 0.0, 1.0]
    assert vector_store.add(v1, "vec1", "error", "err1", "api", 3) is True
    assert vector_store.add(v2, "vec2", "error", "err2", "api", 3) is True
    assert vector_store.add(v3, "vec3", "error", "err3", "api", 3) is True

    hits = vector_store.search([1.0, 0.0, 0.0], top_k=2)
    assert [ref for ref, _ in hits] == ["err1", "err2"]
    # 相似度递减
    assert hits[0][1] > hits[1][1]


def test_search_empty_index_returns_empty():
    assert vector_store.search([1.0, 0.0, 0.0], top_k=5) == []


def test_add_wrong_dim_skipped():
    assert vector_store.add([1.0, 0.0, 0.0], "vec1", "error", "err1", "api", 3) is True
    # 索引 dim=3，写入 2 维向量应被跳过
    assert vector_store.add([1.0, 0.0], "vec2", "error", "err2", "api", 2) is False
    stats = vector_store.index_stats()
    assert stats["total"] == 1


def test_rebuild_clears_index():
    vector_store.add([1.0, 0.0, 0.0], "vec1", "error", "err1", "api", 3)
    assert vector_store.index_stats()["total"] == 1
    assert vector_store.rebuild_index() is True
    assert vector_store.index_stats()["total"] == 0
    assert vector_store.search([1.0, 0.0, 0.0]) == []


# --- 2026-10-04：_index_root() 与索引可观测性 ---


def _reload_index_root(monkeypatch, db_url: str, vector_dir: str):
    """改配置后重新求值 _index_root()，返回新解析出的目录。"""
    import config

    monkeypatch.setattr(config.settings, "database_url", db_url, raising=False)
    monkeypatch.setattr(config.settings, "kb_vector_dir", vector_dir, raising=False)
    return vector_store._index_root()


def test_index_root_prefers_kb_vector_dir_env(monkeypatch, tmp_path):
    # 生产是 Neon（非 SQLite）且显式指定目录 → 用 KB_VECTOR_DIR，不看 cwd
    monkeypatch.setenv("KB_VECTOR_DIR", str(tmp_path))
    monkeypatch.setattr(
        vector_store.settings, "kb_vector_dir", str(tmp_path), raising=False
    )
    root = _reload_index_root(monkeypatch, "postgresql://u:p@host/neondb", str(tmp_path))
    assert root == tmp_path


def test_index_root_non_sqlite_without_env_warns(monkeypatch, caplog):
    # 未设 KB_VECTOR_DIR 且非 SQLite → 回落到 cwd，但必须 warning（不再是静默）
    monkeypatch.setattr(vector_store.settings, "kb_vector_dir", "", raising=False)
    with caplog.at_level(logging.WARNING, logger="vector_store"):
        root = _reload_index_root(
            monkeypatch, "postgresql://u:p@host/neondb", ""
        )
    assert root.name == "kb_vectors"
    assert any("KB_VECTOR_DIR" in r.message for r in caplog.records)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_index_root_sqlite_uses_db_parent(monkeypatch):
    # 留空且是 SQLite → 保持旧逻辑（与 SQLite 同目录），不回归
    monkeypatch.setattr(vector_store.settings, "kb_vector_dir", "", raising=False)
    root = _reload_index_root(monkeypatch, "sqlite:///./somewhere/test.db", "")
    assert root.as_posix().endswith("somewhere/kb_vectors")


def test_index_root_env_overrides_sqlite(monkeypatch, tmp_path):
    # 优先级：KB_VECTOR_DIR 高于 SQLite 同目录
    monkeypatch.setattr(
        vector_store.settings, "kb_vector_dir", str(tmp_path), raising=False
    )
    root = _reload_index_root(monkeypatch, "sqlite:///./somewhere/test.db", str(tmp_path))
    assert root == tmp_path


def test_status_reports_degraded_not_raises_when_index_missing():
    # 索引读不到：状态接口必须正常返回且标degraded，绝不抛错
    status = vector_store.vector_index_status()
    assert status["status"] in {"ok", "degraded"}
    assert "searchMode" in status
    assert "count" in status and "expectedCount" in status
    if status["count"] == 0:
        assert status["searchable"] is False
        assert status["searchMode"] == "name_fuzzy"
        assert status["problems"], "空索引必须给出 problems 说明，不能是空列表"


def test_status_flags_count_mismatch(monkeypatch):
    # 条目数与基准不符必须被标出来，且提示先查同步性而非直接重建
    monkeypatch.setattr(
        vector_store.settings, "kb_vector_expected_count", 99999, raising=False
    )
    vector_store.add([1.0, 0.0, 0.0], "vec1", "point", "p1", "api", 3)
    status = vector_store.vector_index_status()
    assert status["status"] == "degraded"
    assert status["expectedCount"] == 99999
    joined = " ".join(status["problems"])
    assert "99999" in joined and "不要直接重建索引" in joined


def test_status_ok_when_count_matches(monkeypatch):
    monkeypatch.setattr(
        vector_store.settings, "kb_vector_expected_count", 2, raising=False
    )
    vector_store.add([1.0, 0.0, 0.0], "vec1", "point", "p1", "api", 3)
    vector_store.add([0.0, 1.0, 0.0], "vec2", "point", "p2", "api", 3)
    status = vector_store.vector_index_status()
    assert status["count"] == 2
    assert status["refs"] == 2
    assert status["problems"] == []
    assert status["status"] == "ok"
    assert status["searchMode"] == "vector"


def test_search_still_degrades_when_no_index():
    # 索引为空时 search 仍返回 []（降级路径不被破坏）
    assert vector_store.search([1.0, 0.0, 0.0], top_k=3) == []

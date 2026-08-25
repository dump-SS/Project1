"""vector_store FAISS 实装测试（S0-T7b）。

覆盖：
- add → search 命中 Top-K 且相似度递减
- 空索引 search 返回 []
- 维度不一致 add 被跳过
- rebuild 清空索引
"""
from __future__ import annotations

import pytest

import vector_store

pytestmark = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("faiss"),
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

# -*- coding: utf-8 -*-
"""命名空间物理隔离测试（2026-10-06，开关冲突案 · 方案 B）。

验证的核心命题：**用户内容向量与 KB 向量存在不同的磁盘文件上，
写用户内容不可能改到 KB 索引的任何一个字节。**
"""
from __future__ import annotations

import json

import pytest

import vector_store


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """每个用例独立索引目录，避免碰真实索引。"""
    monkeypatch.setattr(vector_store.settings, "kb_vector_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(vector_store, "VECTOR_INDEX_DIR", tmp_path)
    vector_store._indexes.clear()
    vector_store._refs_by_store.clear()
    yield


def test_store_dirs_are_physically_distinct(tmp_path):
    """KB 与 user 命名空间解析到不同目录（这是「物理隔离」的定义）。"""
    kb_dir = vector_store._store_dir(vector_store.STORE_KB)
    user_dir = vector_store._store_dir(vector_store.STORE_USER)
    assert kb_dir == tmp_path
    assert user_dir == tmp_path / "user"
    assert kb_dir != user_dir
    assert vector_store._index_file(vector_store.STORE_KB) != vector_store._index_file(
        vector_store.STORE_USER
    )


def test_kb_store_path_unchanged():
    """KB 命名空间沿用根目录 —— 既有路径零变化（不改动生产行为）。"""
    assert vector_store._index_file(vector_store.STORE_KB).name == "embeddings.index"
    assert vector_store._index_file(vector_store.STORE_KB).parent == vector_store.VECTOR_INDEX_DIR


def test_unknown_store_rejected():
    with pytest.raises(ValueError):
        vector_store._store_dir("nonexistent")


def test_user_add_does_not_touch_kb_index(tmp_path):
    """🔴 核心命题：写用户内容后，KB 索引文件**不存在/未被创建**。"""
    kb_file = vector_store._index_file(vector_store.STORE_KB)
    user_file = vector_store._index_file(vector_store.STORE_USER)

    ok = vector_store.add([1.0, 0.0, 0.0], "ve1", "error", "err1", "local", 3, store=vector_store.STORE_USER)
    assert ok is True
    assert user_file.exists(), "用户索引应已落盘"
    assert not kb_file.exists(), "🔴 KB 索引文件绝不该被创建/触碰"

    # 用户 refs 有 1 条，KB refs 为空
    user_refs = json.loads(vector_store._refs_file(vector_store.STORE_USER).read_text(encoding="utf-8"))
    assert len(user_refs) == 1
    assert user_refs[0]["refId"] == "err1"
    assert not vector_store._refs_file(vector_store.STORE_KB).exists()


def test_kb_add_does_not_touch_user_index(tmp_path):
    """反向：写 KB 不影响用户索引。"""
    kb_file = vector_store._index_file(vector_store.STORE_KB)
    user_file = vector_store._index_file(vector_store.STORE_USER)

    ok = vector_store.add([1.0, 0.0, 0.0], "v1", "point", "p1", "api", 3)
    assert ok is True
    assert kb_file.exists()
    assert not user_file.exists()


def test_both_stores_coexist_independently(tmp_path):
    """两个命名空间并存、各自计数独立、互不串行号。"""
    vector_store.add([1.0, 0.0, 0.0], "kp1", "point", "p1", "api", 3, store=vector_store.STORE_KB)
    vector_store.add([0.0, 1.0, 0.0], "kp2", "point", "p2", "api", 3, store=vector_store.STORE_KB)
    vector_store.add([0.0, 0.0, 1.0], "ve1", "error", "e1", "local", 3, store=vector_store.STORE_USER)

    assert vector_store.index_stats(store=vector_store.STORE_KB)["total"] == 2
    assert vector_store.index_stats(store=vector_store.STORE_USER)["total"] == 1


def test_search_is_namespace_scoped(tmp_path):
    """检索也按命名空间隔离：KB 检索看不到用户向量，反之亦然。"""
    vector_store.add([1.0, 0.0, 0.0], "kp1", "point", "p1", "api", 3, store=vector_store.STORE_KB)
    vector_store.add([1.0, 0.0, 0.0], "ve1", "error", "e1", "local", 3, store=vector_store.STORE_USER)

    kb_hits = vector_store.search([1.0, 0.0, 0.0], store=vector_store.STORE_KB)
    user_hits = vector_store.search([1.0, 0.0, 0.0], store=vector_store.STORE_USER)

    assert [h[0] for h in kb_hits] == ["p1"]
    assert [h[0] for h in user_hits] == ["e1"]


def test_rebuild_is_namespace_scoped(tmp_path):
    """rebuild 只清自己那个命名空间。"""
    vector_store.add([1.0, 0.0, 0.0], "kp1", "point", "p1", "api", 3, store=vector_store.STORE_KB)
    vector_store.add([1.0, 0.0, 0.0], "ve1", "error", "e1", "local", 3, store=vector_store.STORE_USER)

    assert vector_store.rebuild_index(store=vector_store.STORE_USER) is True
    assert vector_store.index_stats(store=vector_store.STORE_USER)["total"] == 0
    # KB 不受影响
    assert vector_store.index_stats(store=vector_store.STORE_KB)["total"] == 1


def test_status_reports_user_store_separately(tmp_path):
    """诊断接口把用户索引单列，且用户条数不参与 KB 的 status 判定。"""
    vector_store.add([1.0, 0.0, 0.0], "kp1", "point", "p1", "api", 3, store=vector_store.STORE_KB)
    vector_store.add([1.0, 0.0, 0.0], "ve1", "error", "e1", "local", 3, store=vector_store.STORE_USER)

    status = vector_store.vector_index_status()
    assert status["count"] == 1  # 只数 KB
    assert status["userStore"]["count"] == 1
    assert "user" in status["userStore"]["indexDir"].replace("\\", "/")

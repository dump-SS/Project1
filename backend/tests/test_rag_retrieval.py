"""T8 RAG 检索链路测试（error-parse 向量召回路径）。

覆盖 `_retrieve_error_points` 的两条路径：
- 路径 1：错题已绑定知识点（kb_error_points）
- 路径 2（T8 新增）：错题原文向量召回——mock embed_text/vector_search，
  覆盖 point 类型 ref、error 类型 ref、embedding off、向量失败降级 四态。
"""
from __future__ import annotations

import pytest

from database import SessionLocal
from models.knowledge import ErrorPoint, ErrorRecord, KnowledgePoint
from routes.knowledge import _retrieve_error_points


def _seed(monkeypatch, subject: str = "math") -> str:
    """造错题 + 2 个知识点（其中 1 个绑定到错题），返回 error_id。"""
    db = SessionLocal()
    try:
        db.add(ErrorRecord(
            id="err_t8", user_id="u_t8", subject=subject,
            raw_text="函数在区间上单调递增怎么判断",
        ))
        db.add(KnowledgePoint(
            id="kp_bound", subject_code=subject, code="math.func.mono",
            name="函数单调性", definition="随自变量增减的性质", error_tip="注意定义域",
        ))
        db.add(KnowledgePoint(
            id="kp_unbound", subject_code=subject, code="math.deriv",
            name="导数与极值", definition="一阶导数求极值", error_tip="注意二阶导",
        ))
        db.add(ErrorPoint(id="erp_1", error_id="err_t8", point_id="kp_bound", confidence=1.0))
        db.commit()
    finally:
        db.close()
    return "err_t8"


def test_linked_points_path_without_embedding(monkeypatch):
    """embedding off：只走路径 1（已绑定知识点）。"""
    _seed(monkeypatch)
    monkeypatch.setattr("embedding_service.embed_mode", lambda: "off")
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "函数单调性" in names
    assert "导数与极值" not in names  # 未绑定且无向量 → 不召回


def test_vector_recall_point_ref(monkeypatch):
    """向量库命中 point 类型 ref → 直接取知识点，与绑定并集。"""
    _seed(monkeypatch)
    monkeypatch.setattr("embedding_service.embed_mode", lambda: "api")
    monkeypatch.setattr("embedding_service.embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        "vector_store.search",
        lambda vec, top_k=5, subject=None: [("kp_unbound", 0.9)],
    )
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "函数单调性" in names  # 路径 1
    assert "导数与极值" in names  # 路径 2（point ref）
    assert out[0]["definition"]  # 元信息非空


def test_vector_recall_error_ref(monkeypatch):
    """向量库命中 error 类型 ref → 取该错题的关联知识点。"""
    err2 = _seed(monkeypatch)
    db = SessionLocal()
    try:
        db.add(ErrorRecord(
            id="err_similar", user_id="u_t8", subject="math",
            raw_text="判断复合函数的单调性",
        ))
        db.add(ErrorPoint(id="erp_2", error_id="err_similar", point_id="kp_unbound", confidence=1.0))
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr("embedding_service.embed_mode", lambda: "api")
    monkeypatch.setattr("embedding_service.embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        "vector_store.search",
        lambda vec, top_k=5, subject=None: [("err_similar", 0.85)],
    )
    out = _retrieve_error_points(err2)
    names = {p["name"] for p in out}
    assert "导数与极值" in names  # 经相似错题召回
    assert "函数单调性" in names  # 原绑定仍在


def test_vector_recall_failure_falls_back(monkeypatch):
    """向量召回失败（embed_text None）→ 静默降级，仅返回路径 1 结果，不报错。"""
    _seed(monkeypatch)
    monkeypatch.setattr("embedding_service.embed_mode", lambda: "api")
    monkeypatch.setattr("embedding_service.embed_text", lambda text: None)
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert names == {"函数单调性"}


def test_vector_recall_cross_subject_filtered(monkeypatch):
    """跨学科召回被过滤：英语知识点不进入数学错题的检索结果。"""
    _seed(monkeypatch, subject="math")
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_en", subject_code="english", code="eng.tense",
            name="时态辨析", definition="动词时态", error_tip="注意主谓一致",
        ))
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr("embedding_service.embed_mode", lambda: "api")
    monkeypatch.setattr("embedding_service.embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        "vector_store.search",
        lambda vec, top_k=5, subject=None: [("kp_en", 0.99), ("kp_bound", 0.8)],
    )
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "时态辨析" not in names  # 跨学科被过滤
    assert "函数单调性" in names

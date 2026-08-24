"""板块二知识库 5 个只读 API 测试（v2.1-B3）。

conftest 每用例清空 DB，所以这里用模块级 conftest 化 seed：
在每个用例前注入数学学科 + 2 个知识点 + 1 条关系。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.knowledge import KnowledgePoint, KnowledgePointRelation, KnowledgeSubject

client = TestClient(app)


@pytest.fixture(autouse=True)
def _seed_kb():
    db = SessionLocal()
    try:
        db.add(KnowledgeSubject(id="ks_math", code="math", name="数学", version="1.0", enabled=True))
        db.flush()
        db.add(KnowledgePoint(
            id="kp_1", subject_code="math", code="math.func", name="函数",
            definition="函数是集合间的对应关系", error_tip="注意定义域", difficulty=2, exam_weight=0.1,
        ))
        db.add(KnowledgePoint(
            id="kp_2", subject_code="math", code="math.func.monotonicity", name="函数单调性",
            definition="随自变量增减的性质", parent_id="kp_1", difficulty=3, exam_weight=0.05,
        ))
        db.add(KnowledgePointRelation(
            id="kpr_1", src_id="kp_1", dst_id="kp_2", type="prerequisite", weight=0.9,
        ))
        db.commit()
    finally:
        db.close()
    yield


def test_subjects_list():
    r = client.get("/api/v1/knowledge/subjects")
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["subjectCode"] == "math"
    assert body["items"][0]["pointCount"] == 2


def test_points_list():
    r = client.get("/api/v1/knowledge/subjects/math/points")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2


def test_point_detail_has_relations():
    r = client.get("/api/v1/knowledge/points/kp_1")
    assert r.status_code == 200
    body = r.json()
    assert body["pointId"] == "kp_1"
    assert any(rel["dstPointId"] == "kp_2" for rel in body["relations"])


def test_graph_placeholder():
    r = client.get("/api/v1/knowledge/subjects/math/graph")
    assert r.status_code == 200
    body = r.json()
    assert body["subjectCode"] == "math"
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1


def test_match_fuzzy_fallback():
    r = client.get("/api/v1/knowledge/points/match", params={"text": "函数 单调性", "subject": "math"})
    assert r.status_code == 200
    body = r.json()
    assert body["matchedBy"] == "keyword_fallback"
    assert len(body["items"]) >= 1


def test_point_404():
    r = client.get("/api/v1/knowledge/points/kp_no")
    assert r.status_code == 404

"""板块二 v2.3 薄弱路径高亮 + StudyGuide 短板提示测试。

覆盖：
- GET /knowledge/subjects/{code}/graph 的 weakPointIds（mastery<0.4 且样本充足）
- POST /plans 的 weaknessHints（mastery<0.7 升序 Top-3）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.goal import Goal as GoalORM
from models.knowledge import (
    ErrorPoint as ErrorPointORM,
    ErrorRecord as ErrorRecordORM,
    KnowledgePoint as KnowledgePointORM,
    KnowledgeSubject as KnowledgeSubjectORM,
)

client = TestClient(app)

HDR = {"X-User-ID": "u_test_weak"}


@pytest.fixture(autouse=True)
def _seed():
    """数学学科 + 2 知识点；kp_2 挂 3 条未解决错题 → mastery≈0.35（<0.4 弱）。"""
    db = SessionLocal()
    try:
        db.add(KnowledgeSubjectORM(id="ks_math", code="math", name="数学", version="1.0", enabled=True))
        db.flush()
        db.add(KnowledgePointORM(
            id="kp_1", subject_code="math", code="math.func", name="函数",
            definition="函数是集合间的对应关系", difficulty=2, exam_weight=0.1,
        ))
        db.add(KnowledgePointORM(
            id="kp_2", subject_code="math", code="math.func.mono", name="函数单调性",
            definition="随自变量增减的性质", parent_id="kp_1", difficulty=3, exam_weight=0.05,
        ))
        db.add(GoalORM(
            id="g_weak", user_id="u_test_weak", type="short_term", subject="math",
            title="函数专项", status="active",
        ))
        for i in range(3):
            eid = f"err_{i}"
            db.add(ErrorRecordORM(
                id=eid, user_id="u_test_weak", subject="math",
                raw_text=f"错题 {i}", status="open",
            ))
            db.add(ErrorPointORM(id=f"ep_{i}", error_id=eid, point_id="kp_2", confidence=1.0))
        db.commit()
    finally:
        db.close()
    yield


def test_graph_weak_point_ids():
    r = client.get("/api/v1/knowledge/subjects/math/graph", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert "weakPointIds" in body
    assert "kp_2" in body["weakPointIds"]
    assert "kp_1" not in body["weakPointIds"]  # kp_1 无数据，样本不足


def test_graph_weak_point_ids_empty_when_no_mastery():
    # 换一个无错题记录的用户，应返回空数组
    r = client.get("/api/v1/knowledge/subjects/math/graph", headers={"X-User-ID": "u_other"})
    assert r.status_code == 200
    assert r.json()["weakPointIds"] == []


def test_plan_weakness_hints():
    r = client.post(
        "/api/v1/plans",
        json={"planDate": "2026-08-24", "availableMinutes": 60},
        headers=HDR,
    )
    assert r.status_code == 201
    hints = r.json().get("weaknessHints", [])
    assert len(hints) >= 1
    assert hints[0]["pointId"] == "kp_2"
    assert hints[0]["mastery"] < 0.4


def test_plan_weakness_hints_empty_for_cold_start():
    # 无目标/无 mastery 的用户，weaknessHints 为空数组而非缺失
    r = client.post(
        "/api/v1/plans",
        json={"planDate": "2026-08-25", "availableMinutes": 60},
        headers={"X-User-ID": "u_cold"},
    )
    assert r.status_code == 201
    assert r.json().get("weaknessHints", []) == []

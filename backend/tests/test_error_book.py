"""板块二错题本 CRUD + 复习测试（v2.1-B6 / v2.2-B5 复习）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.knowledge import ErrorRecord as ErrorRecordORM, KnowledgePoint, ReviewLog

client = TestClient(app)

HDR = {"X-User-ID": "u_test_err"}


@pytest.fixture(autouse=True)
def _seed_kp():
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_1", subject_code="math", code="math.func", name="函数",
            definition="函数是集合间的对应关系", difficulty=2, exam_weight=0.1,
        ))
        db.commit()
    finally:
        db.close()
    yield


def _create(body):
    return client.post("/api/v1/error-book", json=body, headers=HDR)


def test_create_and_get_error():
    r = _create({"subject": "math", "rawText": "求 f(x)=e^(x²) 的极值", "errorType": "concept"})
    assert r.status_code == 201
    err_id = r.json()["errorId"]
    assert err_id.startswith("err_")

    g = client.get(f"/api/v1/error-book/{err_id}", headers=HDR)
    assert g.status_code == 200
    body = g.json()
    assert body["rawText"] == "求 f(x)=e^(x²) 的极值"
    assert body["subject"] == "math"
    assert body["status"] == "open"


def test_create_rejects_sensitive_payload():
    r = _create({"subject": "math", "rawText": "联系电话 13812345678，这道题怎么做"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_create_rejects_too_long_text():
    r = _create({"subject": "math", "rawText": "长" * 4001})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "KB_TEXT_TOO_LONG"


def test_list_filters_soft_deleted_out():
    _create({"subject": "math", "rawText": "题1"})
    e2 = _create({"subject": "math", "rawText": "题2"}).json()["errorId"]
    client.delete(f"/api/v1/error-book/{e2}", headers=HDR)

    r = client.get("/api/v1/error-book", headers=HDR)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_patch_status_and_points():
    err_id = _create({"subject": "math", "rawText": "求极值"}).json()["errorId"]
    r = client.patch(
        f"/api/v1/error-book/{err_id}",
        json={"status": "resolved", "pointIds": ["kp_1"]},
        headers=HDR,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved"
    assert body["points"][0]["pointId"] == "kp_1"


def test_delete_soft_and_get_404():
    err_id = _create({"subject": "math", "rawText": "题"}).json()["errorId"]
    d = client.delete(f"/api/v1/error-book/{err_id}", headers=HDR)
    assert d.status_code == 200 and d.json()["deleted"] is True

    g = client.get(f"/api/v1/error-book/{err_id}", headers=HDR)
    assert g.status_code == 404


def test_review_logs_and_intervals():
    err_id = _create({"subject": "math", "rawText": "题"}).json()["errorId"]
    r = client.post(
        f"/api/v1/error-book/{err_id}/review",
        json={"recallCorrect": True},
        headers=HDR,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["correct"] is True
    assert body["intervalDays"] in (1, 2)

    # 再来一次正确：间隔应进一档（取决于 REVIEW_INTERVALS），此处只断言字段存在
    r2 = client.post(
        f"/api/v1/error-book/{err_id}/review",
        json={"recallCorrect": True},
        headers=HDR,
    )
    assert r2.status_code == 200
    assert r2.json()["intervalDays"] >= r.json()["intervalDays"]

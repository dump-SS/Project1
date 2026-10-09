"""/exams 系列测试（D49 考试独立实体）。

覆盖：CRUD、分数校验（不超满分）、归属隔离（跨用户读不到）、
被 Goal 引用时拒绝删除、以及 Goal 通过 examId + targetScore 引用考试。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

HDR = {"X-User-ID": "u_test_exam"}
HDR_B = {"X-User-ID": "u_test_exam_other"}


def _create(**over):
    body = {"subject": "SX", "name": "期中考试", "examDate": "2026-11-05", "fullScore": 150}
    body.update(over)
    return client.post("/api/v1/exams", json=body, headers=HDR)


def test_create_exam_without_score():
    """考前先把日程记下来是正常用法：score 必须可空，且不能兜成 0（0 分与未回填是两回事）。"""
    r = _create()
    assert r.status_code == 201
    body = r.json()
    assert body["examId"].startswith("e_")
    assert body["score"] is None
    assert body["fullScore"] == 150
    assert body["subject"] == "SX"
    assert body["examDate"] == "2026-11-05"


def test_create_rejects_score_over_full_score():
    r = _create(score=160)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "score"


def test_backfill_score():
    exam_id = _create().json()["examId"]
    r = client.patch(f"/api/v1/exams/{exam_id}", json={"score": 118}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["score"] == 118
    # 未传的字段不能被顺手清掉
    assert r.json()["name"] == "期中考试"


def test_backfill_score_can_be_revoked():
    """显式传 null = 撤回回填（分数记错科目时）。与「不传=不动」必须区分。"""
    exam_id = _create(score=118).json()["examId"]
    r = client.patch(f"/api/v1/exams/{exam_id}", json={"score": None}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["score"] is None


def test_backfill_score_checked_against_full_score():
    exam_id = _create().json()["examId"]
    r = client.patch(f"/api/v1/exams/{exam_id}", json={"score": 200}, headers=HDR)
    assert r.status_code == 400


def test_list_filters_by_subject():
    _create(subject="SX", name="数学期中")
    _create(subject="WL", name="物理月考")
    r = client.get("/api/v1/exams?subject=WL", headers=HDR)
    assert r.status_code == 200
    names = [x["name"] for x in r.json()["items"]]
    assert names == ["物理月考"]


def test_exam_is_user_scoped():
    exam_id = _create().json()["examId"]
    # 另一个用户看不到、也改不动
    assert client.get(f"/api/v1/exams/{exam_id}", headers=HDR_B).status_code == 404
    assert client.patch(
        f"/api/v1/exams/{exam_id}", json={"score": 1}, headers=HDR_B
    ).status_code == 404
    assert client.delete(f"/api/v1/exams/{exam_id}", headers=HDR_B).status_code == 404


def test_delete_exam_blocked_while_referenced_by_goal():
    """被目标引用时拒绝删除——否则 goal.examId 变悬空引用，界面上无法解释。"""
    exam_id = _create().json()["examId"]
    g = client.post(
        "/api/v1/goals",
        json={"type": "short_term", "subject": "SX", "title": "期中数学 120+",
              "examId": exam_id, "targetScore": 120},
        headers=HDR,
    )
    assert g.status_code == 201
    assert g.json()["examId"] == exam_id
    assert g.json()["targetScore"] == 120

    blocked = client.delete(f"/api/v1/exams/{exam_id}", headers=HDR)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "STATE_CONFLICT"

    # 解绑后即可删除
    goal_id = g.json()["goalId"]
    unbound = client.patch(f"/api/v1/goals/{goal_id}", json={"examId": None}, headers=HDR)
    assert unbound.status_code == 200
    assert unbound.json()["examId"] is None
    assert client.delete(f"/api/v1/exams/{exam_id}", headers=HDR).status_code == 200


def test_goal_rejects_unknown_exam():
    r = client.post(
        "/api/v1/goals",
        json={"type": "short_term", "subject": "SX", "title": "指向不存在的考试",
              "examId": "e_nope"},
        headers=HDR,
    )
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "examId"


def test_goal_cannot_reference_other_users_exam():
    exam_id = _create().json()["examId"]
    r = client.post(
        "/api/v1/goals",
        json={"type": "short_term", "subject": "SX", "title": "偷别人的考试",
              "examId": exam_id},
        headers=HDR_B,
    )
    assert r.status_code == 400

"""题本升格（D48）测试：错因 + 意图两正交维度，mastery 只消费「有错因」的。

对照实验是本文的核心：同一个知识点上，挂 3 条**只有意图**的 star 题与 3 条
**有错因**的错题，前者的 mastery 样本量必须是 0、后者必须是 3。
这条断言守的是 D48 的硬口径——star 题（"我觉得这题好"）不得污染掌握度
（"我掌握得怎么样"）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models.knowledge import KnowledgePoint

client = TestClient(app)

HDR = {"X-User-ID": "u_test_topic_book"}

# 两个知识点分别承接「有错因」与「只有意图」两组样本，互不干扰
POINT_SCORED = "kp_d48_scored"
POINT_STAR = "kp_d48_star"


@pytest.fixture(autouse=True)
def _seed_points():
    db = SessionLocal()
    try:
        for pid, code, name in (
            (POINT_SCORED, "d48.scored", "计分点"),
            (POINT_STAR, "d48.star", "star 点"),
        ):
            db.add(KnowledgePoint(
                id=pid, subject_code="SX", code=code, name=name,
                definition="测试用知识点", difficulty=2, exam_weight=0.5,
            ))
        db.commit()
    finally:
        db.close()
    yield


def _create(**kw) -> dict:
    body: dict = {"subject": "SX", "rawText": kw.pop("raw_text", "题面")}
    body.update(kw)
    r = client.post("/api/v1/error-book", json=body, headers=HDR)
    assert r.status_code == 201, r.text
    return r.json()


def _mastery(point_id: str) -> dict:
    r = client.get(f"/api/v1/mastery/points/{point_id}", headers=HDR)
    assert r.status_code == 200, r.text
    return r.json()


def test_two_dimensions_persisted_orthogonally():
    """错因与意图是两个正交维度：可只填其一、可都填、可都不填。"""
    both = _create(
        raw_text="错题：概念不清且想复习",
        pointIds=[POINT_SCORED],
        errorCause="concept_unclear",
        intent="review",
    )
    assert both["errorCause"] == "concept_unclear"
    assert both["intent"] == "review"

    star = _create(raw_text="好题收藏", pointIds=[POINT_STAR], intent="good")
    assert star["errorCause"] is None
    assert star["intent"] == "good"

    plain = _create(raw_text="只有错因", pointIds=[POINT_SCORED], errorCause="careless")
    assert plain["errorCause"] == "careless"
    assert plain["intent"] is None


def test_mastery_only_consumes_items_with_cause():
    """核心断言：star 题（无错因）不进 mastery 样本。"""
    for i in range(3):
        _create(raw_text=f"错题{i}", pointIds=[POINT_SCORED], errorCause="misreading")
    for i in range(3):
        _create(raw_text=f"好题{i}", pointIds=[POINT_STAR], intent="good")

    scored = _mastery(POINT_SCORED)
    star = _mastery(POINT_STAR)

    # 有错因的三条计入样本；只有意图的三条一条都不计
    assert scored["sampleSize"] >= 3, scored
    assert scored["dataSufficient"] is True, scored
    assert star["sampleSize"] == 0, star
    assert star["dataSufficient"] is False, star
    assert star["mastery"] is None, star


def test_star_items_still_reviewable():
    """star 题照样进艾宾浩斯复习队列（只是不喂 mastery）。"""
    item = _create(raw_text="好题", pointIds=[POINT_STAR], intent="typical")
    r = client.post(
        f"/api/v1/error-book/{item['errorId']}/review",
        json={"recallCorrect": True},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["intervalDays"] >= 1

    # 复习过了也不会把无错因的题记进 mastery
    assert _mastery(POINT_STAR)["sampleSize"] == 0


def test_invalid_dimensions_rejected():
    """非法取值 400，不静默丢弃——静默丢弃会让「以为存了其实没存」。"""
    r = client.post(
        "/api/v1/error-book",
        json={"subject": "SX", "rawText": "题", "errorCause": "not_a_cause"},
        headers=HDR,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert r.json()["error"]["field"] == "errorCause"

    r = client.post(
        "/api/v1/error-book",
        json={"subject": "SX", "rawText": "题", "intent": "not_an_intent"},
        headers=HDR,
    )
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "intent"


def test_list_filters_by_each_dimension():
    _create(raw_text="A", errorCause="calculation_error", intent="review")
    _create(raw_text="B", errorCause="knowledge_gap", intent="good")
    _create(raw_text="C", intent="typical")

    by_cause = client.get(
        "/api/v1/error-book", params={"errorCause": "calculation_error"}, headers=HDR
    ).json()
    assert [i["rawText"] for i in by_cause["items"]] == ["A"]

    by_intent = client.get(
        "/api/v1/error-book", params={"intent": "good"}, headers=HDR
    ).json()
    assert [i["rawText"] for i in by_intent["items"]] == ["B"]

    # 两维度组合是「且」
    both = client.get(
        "/api/v1/error-book",
        params={"errorCause": "knowledge_gap", "intent": "good"},
        headers=HDR,
    ).json()
    assert [i["rawText"] for i in both["items"]] == ["B"]


def test_source_exam_id_set_and_cleared():
    """sourceExamId 显式传 null 表示清除（契约里只有它支持 nullable 清除）。"""
    item = _create(raw_text="来自考试", sourceExamId="exam_001")
    assert item["sourceExamId"] == "exam_001"

    cleared = client.patch(
        f"/api/v1/error-book/{item['errorId']}",
        json={"sourceExamId": None},
        headers=HDR,
    )
    assert cleared.status_code == 200
    assert cleared.json()["sourceExamId"] is None


def test_patch_adds_cause_then_mastery_picks_it_up():
    """star 题补上错因后应转为「错题」并被 mastery 消费（错因从无到有）。"""
    item = _create(raw_text="先当 star 收进来", pointIds=[POINT_SCORED], intent="doubtful")
    assert _mastery(POINT_SCORED)["sampleSize"] == 0

    r = client.patch(
        f"/api/v1/error-book/{item['errorId']}",
        json={"errorCause": "concept_unclear"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["errorCause"] == "concept_unclear"
    assert _mastery(POINT_SCORED)["sampleSize"] >= 1

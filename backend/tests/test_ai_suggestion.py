"""AI 建议/复盘链路集成测试（默认 MockProvider）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _post_record(subject: str, hour: str, focus: int = 4, fatigue: int = 2):
    return client.post(
        "/api/v1/learning-records",
        json={
            "subject": subject,
            "startedAt": f"2026-08-12T{hour}:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed", "accuracy": 0.8, "interruptions": 1},
            "selfReport": {
                "focus": focus,
                "fatigue": fatigue,
                "emotion": "positive",
                "difficultyFeel": "moderate",
            },
        },
    )


def test_record_creates_real_recommendation_then_poll_gets_template():
    """核心闭环：POST record 创建 pending 行，轮询同 id 得 ready/template 内容。"""
    # 先积累足够记录，确保 assessment 有真实标签
    _post_record("biology", "08")
    _post_record("biology", "09")
    created = _post_record("biology", "10", focus=4, fatigue=4)

    assert created.status_code == 201
    handle = created.json()["recommendation"]
    assert handle["status"] == "pending"  # 创建响应按契约恒为 pending
    rec_id = handle["recommendationId"]

    # 同步生成已写完，第一次轮询应拿到同一个 id 的 ready/template
    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["recommendationId"] == rec_id
    assert body["generation"]["status"] == "ready"
    assert body["generation"]["source"] == "template"
    assert "completedAt" in body["generation"]
    assert body["items"] and body["items"][0]["title"]
    assert body["basedOn"]["recordId"] == created.json()["recordId"]


def test_skip_recommendation_creates_no_task():
    """skipRecommendation=true 时不创建建议行/句柄。"""
    r = client.post(
        "/api/v1/learning-records",
        json={
            "subject": "history",
            "startedAt": "2026-08-12T11:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed"},
            "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
            "skipRecommendation": True,
        },
    )
    assert r.status_code == 201
    assert r.json()["recommendation"] is None


def test_recommendation_feedback_persists():
    """PUT feedback 应真实写回 ORM，GET 详情可读。"""
    created = _post_record("geography", "08")
    rec_id = created.json()["recommendation"]["recommendationId"]
    put = client.put(f"/api/v1/recommendations/{rec_id}/feedback", json={"rating": "useful", "reason": "很具体"})
    assert put.status_code == 200
    assert put.json()["feedback"]["rating"] == "useful"

    got = client.get(f"/api/v1/recommendations/{rec_id}")
    assert got.json()["feedback"]["reason"] == "很具体"
    assert "submittedAt" in got.json()["feedback"]


def test_summary_insufficient_data_is_not_template():
    """复盘记录不足 → insufficient_data，严格不走 template。"""
    # 此 subject 有少量记录，但整个 period 总记录数依然取当前测试 DB；
    # 用未来区间保证 0 条，稳定验证数据不足分支。
    r = client.post("/api/v1/summaries", json={"periodStart": "2030-01-01", "periodEnd": "2030-01-07"})
    assert r.status_code == 202
    sum_id = r.json()["summaryId"]

    got = client.get(f"/api/v1/summaries/{sum_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["generation"]["status"] == "insufficient_data"
    assert body["generation"].get("source") is None
    assert body["content"] is None
    assert body["dataPoints"]["minRequired"] == 5


def test_summary_mock_provider_fails_not_template():
    """MockProvider 下足够数据的复盘 → failed，符合「复盘不做模板兜底」。"""
    for hour in ["08", "09", "10", "11", "12"]:
        _post_record("politics", hour)

    r = client.post("/api/v1/summaries", json={"periodStart": "2026-08-12", "periodEnd": "2026-08-16"})
    assert r.status_code == 202
    got = client.get(f"/api/v1/summaries/{r.json()['summaryId']}")
    body = got.json()
    assert body["generation"]["status"] == "failed"
    assert body["generation"].get("source") is None
    assert body["content"] is None
    assert body["message"] == "生成失败，请稍后再试"

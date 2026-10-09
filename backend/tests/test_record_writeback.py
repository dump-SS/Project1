"""学习记录事后回写测试（D15）。

核心立场（目标态 §3.7）：学习记录是「可事后回写的活实体」，不是「提交即封存」的快照。
正确率三态可填（结束即填 / 延后补 / 永不填），系统容忍缺失。

本文件盯住两件事：
1. **「不传」与「传 null」必须区分**——否则用户只想改备注会把正确率抹掉；
2. **回写不重复触发评估**（不生成新建议），但状态快照必须重算
   （accuracy 参与算分，不重算会与列表/状态页对不上）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models.recommendation import Recommendation

client = TestClient(app)

HDR = {"X-User-ID": "u_test_writeback"}


def _submit(**over):
    body = {
        "subject": "SX",
        "startedAt": "2026-09-20T19:00:00+08:00",
        "durationMinutes": 45,
        "behavior": {"completion": "partial", "interruptions": 1},
        "selfReport": {"focus": 3, "fatigue": 3, "emotion": "neutral", "difficultyFeel": "moderate"},
    }
    body.update(over)
    return client.post("/api/v1/learning-records", json=body, headers=HDR)


def _rec_count() -> int:
    return len(client.get("/api/v1/learning-records", headers=HDR).json()["items"])


def _recommendation_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Recommendation).filter(
            Recommendation.user_id == "u_test_writeback"
        ).count()
    finally:
        db.close()


def test_submit_then_backfill_accuracy():
    rid = _submit(skipRecommendation=True).json()["recordId"]

    r = client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 0.75}, headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["record"]["behavior"]["accuracy"] == 0.75
    assert body["record"]["recordId"] == rid
    # 回写响应必须带重算后的状态，前端不用再发一次 /assessments/current
    assert body["recalculatedAssessment"]["stateLabel"] == "insufficient_data"


def test_backfill_does_not_touch_unsent_fields():
    rid = _submit(note="函数图像那块看不太进去", skipRecommendation=True).json()["recordId"]

    # 只改正确率 → 备注不能被清掉
    client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 0.6}, headers=HDR)
    got = client.get("/api/v1/learning-records", headers=HDR).json()["items"][0]
    assert got["note"] == "函数图像那块看不太进去"
    assert got["behavior"]["accuracy"] == 0.6


def test_explicit_null_clears_accuracy():
    """显式传 null = 清空（「永不填」那一态），与「不传=别动」区分。"""
    rid = _submit(behavior={"completion": "partial", "accuracy": 0.9, "interruptions": 0},
                  skipRecommendation=True).json()["recordId"]

    r = client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": None}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["record"]["behavior"]["accuracy"] is None


def test_note_is_readable_after_writeback():
    """契约 LearningRecord 有 note 字段，写入后必须能读回来（此前出参缺字段，静默丢弃）。"""
    rid = _submit(skipRecommendation=True).json()["recordId"]
    client.patch(f"/api/v1/learning-records/{rid}", json={"note": "老师讲完才知道对了几道"},
                 headers=HDR)
    got = client.get("/api/v1/learning-records", headers=HDR).json()["items"][0]
    assert got["note"] == "老师讲完才知道对了几道"


def test_writeback_does_not_create_recommendation():
    """D15 验收：回写不重复触发评估——补个正确率不该再推一条建议给用户。"""
    rid = _submit().json()["recordId"]  # 这条会生成一条建议（pending）
    assert _recommendation_count() == 1

    client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 0.8}, headers=HDR)
    client.patch(f"/api/v1/learning-records/{rid}", json={"note": "补个备注"}, headers=HDR)
    assert _recommendation_count() == 1, "回写不得新增建议"


def test_writeback_updates_completion_and_self_report():
    rid = _submit(skipRecommendation=True).json()["recordId"]
    r = client.patch(
        f"/api/v1/learning-records/{rid}",
        json={
            "completion": "completed",
            "selfReport": {"focus": 5, "fatigue": 1, "emotion": "positive", "difficultyFeel": "easy"},
        },
        headers=HDR,
    )
    assert r.status_code == 200
    rec = r.json()["record"]
    assert rec["behavior"]["completion"] == "completed"
    assert rec["selfReport"]["focus"] == 5
    assert rec["selfReport"]["emotion"] == "positive"


def test_writeback_is_user_scoped():
    rid = _submit(skipRecommendation=True).json()["recordId"]
    r = client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 0.5},
                     headers={"X-User-ID": "u_someone_else"})
    assert r.status_code == 404


def test_writeback_rejects_out_of_range_accuracy():
    rid = _submit(skipRecommendation=True).json()["recordId"]
    r = client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 1.5}, headers=HDR)
    # 全局异常处理器把请求校验失败统一成 400 VALIDATION_FAILED（不是 FastAPI 默认的 422）
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "accuracy"


def test_backfill_recomputes_snapshot():
    """攒够 3 条后回写正确率，状态分必须跟着变（accuracy 参与算分）。"""
    ids = [_submit(skipRecommendation=True).json()["recordId"] for _ in range(3)]
    first = client.get("/api/v1/learning-records", headers=HDR).json()["items"]
    assert len(first) == 3

    before = client.get("/api/v1/assessments/current?subject=SX", headers=HDR).json()["items"][0]
    assert before["dataSufficient"] is True

    # 把三条都补成高正确率
    for rid in ids:
        r = client.patch(f"/api/v1/learning-records/{rid}", json={"accuracy": 1.0}, headers=HDR)
        assert r.status_code == 200

    after = client.get("/api/v1/assessments/current?subject=SX", headers=HDR).json()["items"][0]
    assert after["dataSufficient"] is True
    # accuracy 缺省时 w2 归零并重分配；补上高正确率后行为子分必然上升
    assert after["windowScore"] > before["windowScore"]
    assert _rec_count() == 3

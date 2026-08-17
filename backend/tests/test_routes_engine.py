"""路由 ↔ state_engine 集成测试。

验证 POST /learning-records、GET /assessments/current、GET /assessments
真的走 state_engine 计算（而非返回 mock 常量）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _post(subject: str, focus: int, fatigue: int, started: str, emotion: str = "positive"):
    return client.post(
        "/learning-records",
        json={
            "subject": subject,
            "startedAt": started,
            "durationMinutes": 30,
            "behavior": {"completion": "completed", "accuracy": 0.8, "interruptions": 1, "blurCount": 0},
            "selfReport": {
                "focus": focus,
                "fatigue": fatigue,
                "emotion": emotion,
                "difficultyFeel": "moderate",
            },
        },
    )


def test_cold_start_returns_insufficient_data():
    """冷启动：不足 min_records（3）条时，引擎必须返回 insufficient_data
    且不输出 windowScore/trend（PRD 5.2「数据不足时不下结论」）。"""
    r = _post("biology", 5, 1, "2026-08-01T08:00:00+08:00")
    assert r.status_code == 201
    assessment = r.json()["assessment"]
    assert assessment["stateLabel"] == "insufficient_data"
    assert assessment["dataSufficient"] is False
    assert assessment["assessmentId"] is None
    assert assessment.get("windowScore") is None
    assert assessment.get("trend") is None


def test_score_is_engine_computed_not_mock():
    """提交足够记录后，windowScore 必须是引擎算出的真实值（不是 mock 的 0.48）。"""
    for i, hour in enumerate(["08", "09", "10"]):
        r = _post("chemistry", 5, 1, f"2026-08-02T{hour}:00:00+08:00")
    assessment = r.json()["assessment"]
    assert assessment["dataSufficient"] is True
    assert assessment["assessmentId"] is not None
    # 全优记录 → 高分；mock 常量是 0.48，真实计算应远高于它
    assert assessment["windowScore"] > 0.8, f"疑似仍是 mock 值: {assessment}"
    assert assessment["stateLabel"] == "efficient_stable"


def test_trend_reflects_declining_sequence():
    """递减序列（时间戳递增）必须得到 down 趋势——证明趋势来自真实回归计算。"""
    seq = [(5, 1, "08"), (5, 1, "09"), (4, 2, "10"), (3, 3, "11"), (2, 4, "12")]
    last = None
    for focus, fatigue, hour in seq:
        last = _post("physics", focus, fatigue, f"2026-08-03T{hour}:00:00+08:00")
    assessment = last.json()["assessment"]
    assert assessment["trend"] == "down", f"趋势应为 down: {assessment}"


def test_window_ordering_is_deterministic():
    """回归：同一 startedAt 的多条记录，窗口排序必须确定。

    此前只按 started_at 排序，同一时间戳下顺序不定，reversed() 后窗口可能整体
    颠倒，使线性回归斜率符号反转（同一份数据可能算出 up 也可能算出 down）。
    加了 created_at + id 次序键后，重复查询结果必须稳定。

    注：本测试保证的是「确定性」。若 started_at 与 created_at 同时相同（同一秒内
    批量插入），排序退化为按 id，仍无法还原真实插入顺序——彻底解决需要给表加
    自增序列列，属 schema 改动，见 README TODO。
    """
    same_ts = "2026-08-04T10:00:00+08:00"
    for focus, fatigue in [(5, 1), (4, 2), (3, 3), (2, 4)]:
        _post("history", focus, fatigue, same_ts)

    trends = set()
    scores = set()
    for _ in range(5):
        body = client.get("/assessments/current?subject=history").json()
        item = body["items"][0]
        trends.add(item.get("trend"))
        scores.add(item.get("windowScore"))

    assert len(trends) == 1, f"趋势在多次查询间不稳定: {trends}"
    assert len(scores) == 1, f"分数在多次查询间不稳定: {scores}"


def test_current_assessment_has_explainability():
    """GET /assessments/current 必须带 displayText 与 basedOn（PRD 8.3 可解释性）。"""
    for hour in ["08", "09", "10"]:
        _post("geography", 4, 2, f"2026-08-05T{hour}:00:00+08:00")

    body = client.get("/assessments/current?subject=geography").json()
    item = body["items"][0]
    assert item["displayText"], "缺少面向用户的自然语言说明"
    assert item["basedOn"]["recordIds"], "缺少参与计算的记录 ID"
    assert isinstance(item["basedOn"]["signals"], list)
    # 不得暴露权重与公式（PRD 5.2 / 6.1）
    assert "weight" not in str(item).lower()
    assert "alpha" not in str(item).lower()


def test_history_accumulates_snapshots():
    """GET /assessments 返回历史快照序列（每次重算落库一条）。"""
    for hour in ["08", "09", "10", "11"]:
        _post("politics", 4, 2, f"2026-08-06T{hour}:00:00+08:00")

    body = client.get("/assessments?subject=politics").json()
    assert body["subject"] == "politics"
    assert len(body["items"]) >= 1
    point = body["items"][0]
    assert 0 <= point["windowScore"] <= 1
    assert point["stateLabel"] in {
        "efficient_stable",
        "fatigue_warning",
        "emotion_blocked",
        "fluctuating_up",
        "insufficient_data",
    }

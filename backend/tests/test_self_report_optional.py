"""自评软字段可缺（D20 三层收尾 / D34 转译兜底）——引擎与接口两层。

目标态 §3.7(a) 的口径：
> 核心自评**在**（完成度＋情绪，直填）→ 正常算分，软字段缺则**跳过**、按可用部分归一化；
> 核心自评**也缺** → 不硬凑，标签降级。

本文件盯住三件事：
1. **软字段缺失只"变粗"不"变假"**：缺项被跳过并按可用项权重归一化，不是当 0 分；
2. **四字段齐全时结果与放开前逐字节一致**（向后兼容，靠数值断言钉死）；
3. 缺字段**不报错**（原来是 KeyError → 500）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from state_engine.scoring import compute_session_score
from state_engine.types import (
    BehaviorInput,
    Completion,
    Emotion,
    RecordInput,
    SelfReportInput,
    WeightConfig,
)

client = TestClient(app)
HDR = {"X-User-ID": "u_test_selfreport"}


def _behavior(accuracy=None):
    return BehaviorInput(completion=Completion.COMPLETED, accuracy=accuracy)


# ---------- 引擎层 ----------


def test_full_self_report_matches_legacy_formula():
    """四字段齐全 → 与放开前完全相同的公式（不得因为"归一化"引入偏差）。"""
    w = WeightConfig()
    rec = RecordInput(
        behavior=_behavior(accuracy=0.8),
        self_report=SelfReportInput(focus=4, fatigue=2, emotion=Emotion.POSITIVE,
                                    difficulty_feel="moderate"),
    )
    got = compute_session_score(rec, w)

    # 手工复算放开前的原式（interruptions/blur 均为 0 → 节奏稳定度 = 1.0）
    behavior_sub = (1 / 3) * 1.0 + (1 / 3) * 0.8 + (1 / 3) * 1.0
    self_sub = (
        (1 / 3) * ((4 - 1) / 4)          # focus 4 → 0.75
        + (1 / 3) * ((6 - 2 - 1) / 4)    # fatigue 2 → 0.75
        + (1 / 3) * 1.0                  # positive → 1.0
    )
    expected = 0.5 * behavior_sub + 0.5 * self_sub

    assert abs(got.score - expected) < 1e-12
    assert abs(got.self_report_sub - self_sub) < 1e-12


def test_missing_soft_field_is_renormalized_not_zeroed():
    """缺 focus → 该项权重剔除、按剩余两项归一化；**不是**把它当 0 分。

    构造：focus=1（最差项）、fatigue=2、emotion=positive。
    - 若按"缺项当 0 分"处理 → 自评子分 = 0.5833（被拖低）
    - 正确的"跳过并按可用项归一化" → (0.75 + 1.0) / 2 = 0.875
    """
    w = WeightConfig()
    full = compute_session_score(
        RecordInput(behavior=_behavior(), self_report=SelfReportInput(
            focus=1, fatigue=2, emotion=Emotion.POSITIVE, difficulty_feel="moderate")),
        w,
    )
    no_focus = compute_session_score(
        RecordInput(behavior=_behavior(), self_report=SelfReportInput(
            focus=None, fatigue=2, emotion=Emotion.POSITIVE, difficulty_feel="moderate")),
        w,
    )

    assert abs(full.self_report_sub - (1 / 3) * 0.0 - (1 / 3) * 0.75 - (1 / 3) * 1.0) < 1e-12
    assert abs(no_focus.self_report_sub - 0.875) < 1e-12, "缺项必须被跳过并归一化"
    assert no_focus.self_report_sub != full.self_report_sub
    assert no_focus.score > full.score, "丢掉最差项后分数应上升，而不是被 0 拖低"


def test_only_completion_is_enough():
    """三层收尾里只有完成度是半强制的：自评整段缺失也要能算出分。"""
    got = compute_session_score(
        RecordInput(behavior=_behavior(accuracy=0.9), self_report=SelfReportInput()),
        WeightConfig(),
    )
    assert got.self_report_sub is None          # 自评不可用 → 明确置 None，不拿 0 冒充
    assert got.score == got.behavior_sub        # 退化为只按行为子分计
    assert got.score > 0.5


def test_emotion_alone_is_usable():
    got = compute_session_score(
        RecordInput(behavior=_behavior(), self_report=SelfReportInput(emotion=Emotion.NEGATIVE)),
        WeightConfig(),
    )
    assert got.self_report_sub == 0.0  # 只有情绪且为负向 → 自评子分确实是 0（这是"有自评且很差"）
    assert got.score < 1.0


# ---------- 接口层 ----------


def _submit(**over):
    body = {
        "subject": "SX",
        "startedAt": "2026-09-20T19:00:00+08:00",
        "durationMinutes": 45,
        "behavior": {"completion": "completed"},
    }
    body.update(over)
    return client.post("/api/v1/learning-records", json=body, headers=HDR)


def test_submit_without_self_report_at_all():
    r = _submit(skipRecommendation=True)
    assert r.status_code == 201, r.text
    sr = r.json()["selfReport"]
    assert sr == {"focus": None, "fatigue": None, "emotion": None, "difficultyFeel": None}
    # 记录来源默认 self_report
    assert r.json()["source"] == "self_report"
    assert r.json()["sourceExamId"] is None


def test_submit_with_partial_soft_fields():
    r = _submit(selfReport={"emotion": "neutral"}, skipRecommendation=True)
    assert r.status_code == 201, r.text
    sr = r.json()["selfReport"]
    assert sr["emotion"] == "neutral"
    assert sr["focus"] is None and sr["fatigue"] is None


def test_missing_self_report_no_longer_500():
    """放开前 `self_report["focus"]` 会 KeyError → 500；现在必须正常落库。"""
    r = _submit(selfReport={}, skipRecommendation=True)
    assert r.status_code == 201, r.text


def test_self_report_optional_values_are_read_back():
    rid = _submit(selfReport={"focus": 4}, skipRecommendation=True).json()["recordId"]
    got = client.get("/api/v1/learning-records", headers=HDR).json()["items"][0]
    assert got["recordId"] == rid
    assert got["selfReport"]["focus"] == 4
    assert got["selfReport"]["fatigue"] is None


def test_records_filter_by_source():
    _submit(skipRecommendation=True)
    r = client.get("/api/v1/learning-records?source=exam", headers=HDR)
    assert r.status_code == 200
    assert r.json()["items"] == []
    r = client.get("/api/v1/learning-records?source=self_report", headers=HDR)
    assert len(r.json()["items"]) == 1

"""趋势量化 + 标签判定测试。"""

from state_engine.assessment import compute_window_assessment
from state_engine.scoring import compute_session_score
from state_engine.types import (
    BehaviorInput,
    Completion,
    Emotion,
    LabelThresholds,
    RecordInput,
    SelfReportInput,
    StateLabel,
    Trend,
    WeightConfig,
)


def _make_record(focus=4, fatigue=2, emotion=Emotion.POSITIVE, completion=Completion.COMPLETED):
    return RecordInput(
        behavior=BehaviorInput(completion=completion),
        self_report=SelfReportInput(focus=focus, fatigue=fatigue, emotion=emotion, difficulty_feel="moderate"),
    )


def _score(r):
    return compute_session_score(r, WeightConfig())


def test_insufficient_data():
    """少于 min_records 条时返回 insufficient_data。"""
    records = [_make_record() for _ in range(2)]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.state_label == StateLabel.INSUFFICIENT_DATA
    assert not result.data_sufficient
    assert result.window_score is None


def test_efficient_stable():
    """高分 + 平稳趋势 → efficient_stable。"""
    records = [_make_record(focus=5, fatigue=1, emotion=Emotion.POSITIVE) for _ in range(5)]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.state_label == StateLabel.EFFICIENT_STABLE
    assert result.trend in (Trend.FLAT, Trend.UP)


def test_fatigue_warning():
    """低分 + 高疲劳 + 下降趋势 → fatigue_warning。"""
    records = []
    # 逐渐恶化
    for i in range(5):
        records.append(_make_record(focus=3 - min(i, 2), fatigue=3 + min(i, 2), emotion=Emotion.NEGATIVE, completion=Completion.PARTIAL))
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.state_label in (StateLabel.FATIGUE_WARNING, StateLabel.EMOTION_BLOCKED)


def test_emotion_blocked():
    """连续负向情绪 → emotion_blocked。"""
    records = [_make_record(focus=3, fatigue=3, emotion=Emotion.NEGATIVE) for _ in range(5)]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.state_label == StateLabel.EMOTION_BLOCKED
    assert any("情绪" in s for s in result.signals)


def test_fluctuating_up():
    """趋势上升但水平未达高位 → fluctuating_up。"""
    records = []
    for i in range(5):
        records.append(_make_record(focus=2 + i, fatigue=4 - i, emotion=Emotion.NEUTRAL))
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.trend == Trend.UP
    assert result.state_label in (StateLabel.FLUCTUATING_UP, StateLabel.EFFICIENT_STABLE)


def test_mid_flat_no_false_fatigue_warning():
    """回归 P1：中等+平稳、无疲劳/情绪信号，不应被误标疲劳预警。"""
    records = [_make_record(focus=3, fatigue=3, emotion=Emotion.NEUTRAL, completion=Completion.PARTIAL) for _ in range(5)]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.state_label != StateLabel.FATIGUE_WARNING
    assert result.state_label == StateLabel.EFFICIENT_STABLE
    # 信号要如实说明"水平一般但平稳"，而不是无信号
    assert any("平稳" in s for s in result.signals)


def test_high_down_carries_trend_signal():
    """回归 P2：高分+下降趋势保留 efficient_stable，但必须附趋势信号。"""
    # 逐步恶化：分数从 1.0 单调下滑，产生明确 DOWN 趋势但均值仍高位
    records = [
        _make_record(focus=5, fatigue=1),
        _make_record(focus=4, fatigue=2),
        _make_record(focus=3, fatigue=3),
        _make_record(focus=2, fatigue=4),
        _make_record(focus=1, fatigue=5),
    ]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.trend == Trend.DOWN
    assert result.state_label == StateLabel.EFFICIENT_STABLE
    assert any("下降" in s for s in result.signals)


def test_low_flat_warns():
    """回归：低水平无论趋势如何都应提醒（不依赖疲劳信号才预警）。"""
    records = [_make_record(focus=1, fatigue=3, emotion=Emotion.NEUTRAL, completion=Completion.ABANDONED) for _ in range(5)]
    scores = [_score(r) for r in records]
    result = compute_window_assessment(scores, records)
    assert result.data_sufficient
    assert result.state_label == StateLabel.FATIGUE_WARNING

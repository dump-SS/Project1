"""单次状态分计算测试。"""

from state_engine.scoring import compute_session_score, normalize_rhythm
from state_engine.types import (
    BehaviorInput,
    Completion,
    Emotion,
    RecordInput,
    SelfReportInput,
    WeightConfig,
)


def test_normalize_rhythm_negative_input():
    """回归：负中断次数按 0 处理，函数自洽不越界。"""
    assert normalize_rhythm(-3, 0) == 1.0
    assert 0.0 < normalize_rhythm(0, 0) <= 1.0
    assert 0.0 < normalize_rhythm(100, 100) <= 1.0


def _make_record(
    completion=Completion.COMPLETED,
    accuracy=None,
    interruptions=0,
    blur_count=0,
    focus=4,
    fatigue=2,
    emotion=Emotion.POSITIVE,
) -> RecordInput:
    return RecordInput(
        behavior=BehaviorInput(completion=completion, accuracy=accuracy, interruptions=interruptions, blur_count=blur_count),
        self_report=SelfReportInput(focus=focus, fatigue=fatigue, emotion=emotion, difficulty_feel="moderate"),
    )


def test_perfect_score():
    """所有维度最优，默认权重应接近 1.0。"""
    r = _make_record(accuracy=1.0, focus=5, fatigue=1, emotion=Emotion.POSITIVE)
    s = compute_session_score(r, WeightConfig())
    assert 0.9 <= s.score <= 1.0


def test_worst_score():
    """所有维度最差，应接近 0。"""
    r = _make_record(
        completion=Completion.ABANDONED, accuracy=0.0,
        interruptions=20, blur_count=10,
        focus=1, fatigue=5, emotion=Emotion.NEGATIVE,
    )
    s = compute_session_score(r, WeightConfig())
    assert 0.0 <= s.score <= 0.15


def test_no_accuracy_redistribution():
    """accuracy 缺失时 w2 归零，不影响总分范围。"""
    r = _make_record(accuracy=None, focus=3, fatigue=3, emotion=Emotion.NEUTRAL)
    s = compute_session_score(r, WeightConfig())
    assert 0.0 <= s.score <= 1.0
    # 没有 accuracy 不应导致异常或 None
    assert s.behavior_sub >= 0


def test_score_between_0_and_1():
    """任意输入，score 必须在 [0, 1]。"""
    import random
    random.seed(42)
    for _ in range(100):
        r = _make_record(
            completion=random.choice(list(Completion)),
            accuracy=random.random() if random.random() > 0.3 else None,
            interruptions=random.randint(0, 30),
            blur_count=random.randint(0, 20),
            focus=random.randint(1, 5),
            fatigue=random.randint(1, 5),
            emotion=random.choice(list(Emotion)),
        )
        s = compute_session_score(r, WeightConfig())
        assert 0.0 <= s.score <= 1.0, f"score out of range: {s.score}"

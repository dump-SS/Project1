"""mastery 引擎单测（PRD 12.3.4：公式固定 + 置信度规则）。"""
from __future__ import annotations

from mastery_engine import MIN_SAMPLES, MasteryInputs, compute_mastery


def test_insufficient_data_returns_none():
    r = compute_mastery("kp_1", MasteryInputs(error_count=1))
    assert r.data_sufficient is False
    assert r.mastery is None
    assert r.sample_size < MIN_SAMPLES


def test_perfect_mastery():
    r = compute_mastery(
        "kp_1",
        MasteryInputs(
            error_count=3,
            unresolved_count=0,
            review_count=3,
            recall_correct_count=3,
            days_since_last_review=1,
        ),
    )
    assert r.data_sufficient is True
    assert r.mastery is not None
    assert 0.0 <= r.mastery <= 1.0
    # 全对 + 无未解决 + 近度 1 天 → 高分（≥0.8）
    assert r.mastery >= 0.8


def test_unresolved_drags_down():
    r = compute_mastery(
        "kp_1",
        MasteryInputs(
            error_count=4,
            unresolved_count=4,
            review_count=0,
            days_since_last_review=None,
        ),
    )
    assert r.mastery is not None
    assert r.mastery < 0.5


def test_recency_decays():
    near = compute_mastery(
        "kp_1",
        MasteryInputs(error_count=3, unresolved_count=0, review_count=3,
                      recall_correct_count=3, days_since_last_review=0.5),
    )
    far = compute_mastery(
        "kp_1",
        MasteryInputs(error_count=3, unresolved_count=0, review_count=3,
                      recall_correct_count=3, days_since_last_review=40),
    )
    assert near.mastery > far.mastery


def test_weights_are_honored():
    """未解决权重拉满时，未解决错题影响更大。"""
    from mastery_engine import MasteryWeights
    w = MasteryWeights(w_unresolved=1.0, w_error=0, w_accuracy=0, w_recency=0, w_retention=0)
    r = compute_mastery(
        "kp_1",
        MasteryInputs(error_count=3, unresolved_count=3, review_count=0,
                      days_since_last_review=None),
        weights=w,
    )
    # 全未解决 → unresolved_factor=1-0.25*3=0.25
    assert r.mastery is not None
    assert abs(r.mastery - 0.25) < 1e-3

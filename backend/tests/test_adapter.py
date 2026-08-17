"""适配层测试：契约 JSON ↔ 引擎类型的转换正确性。"""

from state_engine.adapter import (
    compute_window_for_records,
    display_text_for,
    record_payload_to_engine,
    window_to_snapshot_payload,
    window_to_state_result_payload,
)
from state_engine.types import (
    BehaviorInput,
    Completion,
    Emotion,
    RecordInput,
    SelfReportInput,
    StateLabel,
)


def _payload(**overrides):
    base = {
        "subject": "math",
        "startedAt": "2026-08-16T19:00:00+08:00",
        "durationMinutes": 45,
        "behavior": {
            "completion": "partial",
            "accuracy": 0.62,
            "interruptions": 3,
            "blurCount": 5,
        },
        "selfReport": {
            "focus": 2,
            "fatigue": 4,
            "emotion": "negative",
            "difficultyFeel": "hard",
        },
    }
    base.update(overrides)
    return base


def test_record_payload_to_engine_full():
    out = record_payload_to_engine(_payload())
    assert out.duration_minutes == 45
    assert out.behavior == BehaviorInput(
        completion=Completion.PARTIAL, accuracy=0.62, interruptions=3, blur_count=5
    )
    assert out.self_report == SelfReportInput(
        focus=2, fatigue=4, emotion=Emotion.NEGATIVE, difficulty_feel="hard"
    )


def test_record_payload_to_engine_defaults():
    """可选字段缺失时按契约默认：interruptions/blurCount 归 0、accuracy 为 None。"""
    out = record_payload_to_engine(
        {
            "behavior": {"completion": "completed"},
            "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive"},
        }
    )
    assert out.behavior.accuracy is None
    assert out.behavior.interruptions == 0
    assert out.behavior.blur_count == 0
    assert out.duration_minutes == 0


def test_compute_window_for_records_sufficient():
    good = record_payload_to_engine(
        {"behavior": {"completion": "completed"}, "selfReport": {"focus": 5, "fatigue": 1, "emotion": "positive"}}
    )
    window = compute_window_for_records([good] * 5)
    assert window.data_sufficient
    assert window.state_label == StateLabel.EFFICIENT_STABLE


def test_compute_window_insufficient():
    one = record_payload_to_engine(
        {"behavior": {"completion": "completed"}, "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive"}}
    )
    window = compute_window_for_records([one])
    assert not window.data_sufficient
    assert window.state_label == StateLabel.INSUFFICIENT_DATA


def test_window_to_snapshot_payload_sufficient():
    good = record_payload_to_engine(
        {"behavior": {"completion": "completed"}, "selfReport": {"focus": 5, "fatigue": 1, "emotion": "positive"}}
    )
    window = compute_window_for_records([good] * 5)
    payload = window_to_snapshot_payload(window, "math", "a_7742")
    assert payload["assessmentId"] == "a_7742"
    assert payload["subject"] == "math"
    assert 0 <= payload["windowScore"] <= 1
    assert payload["trend"] in ("up", "flat", "down")
    assert payload["stateLabel"] == "efficient_stable"
    assert payload["dataSufficient"] is True
    assert payload["recordCount"] == 5


def test_window_to_snapshot_payload_insufficient():
    """数据不足：assessmentId 可空、无 windowScore/trend（v1.1 契约语义）。"""
    one = record_payload_to_engine(
        {"behavior": {"completion": "completed"}, "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive"}}
    )
    window = compute_window_for_records([one])
    payload = window_to_snapshot_payload(window, "math", None)
    assert payload["assessmentId"] is None
    assert "windowScore" not in payload
    assert "trend" not in payload
    assert payload["stateLabel"] == "insufficient_data"


def test_window_to_state_result_payload():
    good = record_payload_to_engine(
        {"behavior": {"completion": "completed"}, "selfReport": {"focus": 5, "fatigue": 1, "emotion": "positive"}}
    )
    window = compute_window_for_records([good] * 5)
    payload = window_to_state_result_payload(window, "math", "a_7742", ["r_1", "r_2", "r_3"])
    assert payload["displayText"]
    assert payload["windowSize"] == 7
    assert payload["basedOn"]["recordIds"] == ["r_1", "r_2", "r_3"]
    assert isinstance(payload["basedOn"]["signals"], list)


def test_display_text_covers_all_labels():
    covered: dict[StateLabel, str] = {}
    for label in StateLabel:
        # 构造一个最小 WindowAssessment 直接验证映射存在
        from state_engine.types import Trend, WindowAssessment

        window = WindowAssessment(
            window_score=None,
            trend=None,
            state_label=label,
            data_sufficient=False,
            record_count=0,
            signals=[],
        )
        text = display_text_for(window)
        assert text, f"displayText 缺失: {label}"
        covered[label] = text
    assert len(covered) == 5
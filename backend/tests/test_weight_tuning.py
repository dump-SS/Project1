"""AI 调权端到端测试（PRD 5.2 第 4 点）。

覆盖：
- 触发条件（按周期 / 记录数阈值 / 用户开关）
- LLM 输出 JSON 围栏容错
- 合法调权落库 + 留痕
- 越界建议回退（不是回退到初始值，而是保持当前权重）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import weight_tuning
from database import SessionLocal
from models.learning_record import LearningRecord
from models.user import Settings as SettingsModel
from models.weight import UserWeightConfig, WeightAdjustLog
from state_engine.types import WeightConfig
from state_engine.weights import WeightAdjustment
from weight_tuning import _should_tune, _suggest_weights, tune_user_weights


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _add_records(user_id: str, count: int, subject: str = "math") -> None:
    db = SessionLocal()
    try:
        for i in range(count):
            db.add(
                LearningRecord(
                    id=f"r_{user_id}_{_uid()}",
                    user_id=user_id,
                    subject=subject,
                    started_at=datetime.utcnow() - timedelta(minutes=i),
                    duration_minutes=30,
                    behavior_completion="completed",
                    behavior_accuracy=0.8,
                    behavior_interruptions=1,
                    behavior_blur_count=0,
                    self_report_focus=5,
                    self_report_fatigue=1,
                    self_report_emotion="positive",
                    self_report_difficulty_feel="easy",
                )
            )
        db.commit()
    finally:
        db.close()


def _add_success_log(user_id: str, effective_at: datetime) -> None:
    db = SessionLocal()
    try:
        db.add(
            WeightAdjustLog(
                id=f"wlog_{user_id}_{_uid()}",
                user_id=user_id,
                before_alpha=0.5, before_beta=0.5,
                before_w1=1 / 3, before_w2=1 / 3, before_w3=1 / 3,
                before_w4=1 / 3, before_w5=1 / 3, before_w6=1 / 3,
                after_alpha=0.5, after_beta=0.5,
                after_w1=1 / 3, after_w2=1 / 3, after_w3=1 / 3,
                after_w4=1 / 3, after_w5=1 / 3, after_w6=1 / 3,
                reason="test",
                reverted=False,
                effective_at=effective_at,
            )
        )
        db.commit()
    finally:
        db.close()


def _set_tuning_enabled(user_id: str, enabled: bool) -> None:
    db = SessionLocal()
    try:
        db.add(
            SettingsModel(
                user_id=user_id,
                ai_weight_tuning_enabled=enabled,
                send_text_to_ai=False,
            )
        )
        db.commit()
    finally:
        db.close()


class _FakeProvider:
    def __init__(self, text: str):
        self._text = text

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        return self._text


# ---------- 触发条件 ----------

def test_should_tune_never_tuned_below_threshold():
    _add_records("u_below", 2)
    db = SessionLocal()
    try:
        assert _should_tune(db, "u_below") is False
    finally:
        db.close()


def test_should_tune_never_tuned_at_threshold():
    _add_records("u_at", 3)
    db = SessionLocal()
    try:
        assert _should_tune(db, "u_at") is True
    finally:
        db.close()


def test_should_tune_within_interval_skips():
    """调权成功后，间隔未到（<7 天）不应再次触发。"""
    _add_records("u_recent", 10)
    _add_success_log("u_recent", datetime.utcnow() - timedelta(days=1))
    db = SessionLocal()
    try:
        assert _should_tune(db, "u_recent") is False
    finally:
        db.close()


def test_should_tune_past_interval_triggers():
    """调权已过间隔（>=7 天）且记录数达标，应再次触发。"""
    _add_records("u_past", 10)
    _add_success_log("u_past", datetime.utcnow() - timedelta(days=8))
    db = SessionLocal()
    try:
        assert _should_tune(db, "u_past") is True
    finally:
        db.close()


def test_should_tune_disabled_by_user():
    _add_records("u_off", 10)
    _set_tuning_enabled("u_off", False)
    db = SessionLocal()
    try:
        assert _should_tune(db, "u_off") is False
    finally:
        db.close()


# ---------- LLM 输出 JSON 围栏容错 ----------

def test_suggest_weights_parses_fenced_json(monkeypatch):
    fenced = (
        '```json\n{"alpha": 0.55, "beta": 0.45, "w1": 0.35, "w2": 0.30, '
        '"w3": 0.35, "w4": 0.40, "w5": 0.30, "w6": 0.30, '
        '"reason": "疲劳信号增强"}\n```'
    )
    monkeypatch.setattr(weight_tuning, "get_provider", lambda: _FakeProvider(fenced))
    adj = _suggest_weights({}, WeightConfig())
    assert isinstance(adj, WeightAdjustment)
    assert adj.alpha == 0.55
    assert adj.reason == "疲劳信号增强"


def test_suggest_weights_returns_none_on_garbage(monkeypatch):
    monkeypatch.setattr(weight_tuning, "get_provider", lambda: _FakeProvider("not json at all"))
    assert _suggest_weights({}, WeightConfig()) is None


# ---------- 完整调权流程 ----------

_VALID_JSON = (
    '{"alpha": 0.55, "beta": 0.45, "w1": 0.35, "w2": 0.30, "w3": 0.35, '
    '"w4": 0.40, "w5": 0.30, "w6": 0.30, "reason": "疲劳信号增强"}'
)

_INVALID_JSON = (
    '{"alpha": 0.8, "beta": 0.2, "w1": 0.33, "w2": 0.33, "w3": 0.34, '
    '"w4": 0.33, "w5": 0.33, "w6": 0.34, "reason": "越界测试"}'
)


def test_tune_valid_updates_and_logs(monkeypatch):
    _add_records("u_valid", 10)
    monkeypatch.setattr(weight_tuning, "get_provider", lambda: _FakeProvider(_VALID_JSON))

    db = SessionLocal()
    try:
        assert tune_user_weights(db, "u_valid") is True
        cfg = db.get(UserWeightConfig, "u_valid")
        assert cfg is not None
        assert abs(cfg.alpha - 0.55) < 1e-6
    finally:
        db.close()

    # 留痕：reverted=False 的成功调权
    db = SessionLocal()
    try:
        logs = db.query(WeightAdjustLog).filter(WeightAdjustLog.user_id == "u_valid").all()
        assert len(logs) == 1
        assert logs[0].reverted is False
        assert logs[0].reason == "疲劳信号增强"
    finally:
        db.close()


def test_tune_invalid_reverts_and_logs(monkeypatch):
    _add_records("u_invalid", 10)
    monkeypatch.setattr(weight_tuning, "get_provider", lambda: _FakeProvider(_INVALID_JSON))

    db = SessionLocal()
    try:
        assert tune_user_weights(db, "u_invalid") is False
        cfg = db.get(UserWeightConfig, "u_invalid")
        assert cfg is not None
        # 回退到当前权重（默认 0.5），不是初始值之外的任何值
        assert abs(cfg.alpha - 0.5) < 1e-6
    finally:
        db.close()

    # 留痕：reverted=True，且带拒绝理由
    db = SessionLocal()
    try:
        logs = db.query(WeightAdjustLog).filter(WeightAdjustLog.user_id == "u_invalid").all()
        assert len(logs) == 1
        assert logs[0].reverted is True
        assert logs[0].revert_reason, "回退时必须记录拒绝理由"
    finally:
        db.close()
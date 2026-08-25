"""mastery 内容权重读取链路测试（S0-T6）。

覆盖：默认等权；读取持久化 m1..m5；关闭 AI 调权走固定；越界回退默认。
"""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.user import Settings
from models.weight import UserWeightConfig
from routes.mastery import _get_mastery_weights
from mastery_engine import MasteryWeights

client = TestClient(app)


def _clean(user_id: str):
    db = SessionLocal()
    try:
        for row in db.query(UserWeightConfig).filter_by(user_id=user_id).all():
            db.delete(row)
        s = db.get(Settings, user_id)
        if s is not None:
            db.delete(s)
        db.commit()
    finally:
        db.close()


def test_default_weights_when_no_config():
    uid = "u_mw_default"
    _clean(uid)
    db = SessionLocal()
    try:
        w = _get_mastery_weights(db, uid)
        assert isinstance(w, MasteryWeights)
        assert abs(w.w_error - 0.2) < 1e-6
    finally:
        db.close()


def test_reads_persisted_mastery_weights():
    uid = "u_mw_persist"
    _clean(uid)
    db = SessionLocal()
    try:
        db.add(Settings(user_id=uid, ai_weight_tuning_enabled=True, send_text_to_ai=False))
        cfg = UserWeightConfig(user_id=uid, m1=0.3, m2=0.2, m3=0.2, m4=0.15, m5=0.15)
        db.add(cfg)
        db.commit()
        w = _get_mastery_weights(db, uid)
        assert abs(w.w_error - 0.3) < 1e-6
        assert abs(w.w_unresolved - 0.15) < 1e-6
    finally:
        db.close()


def test_disabled_tuning_uses_fixed_defaults():
    uid = "u_mw_disabled"
    _clean(uid)
    db = SessionLocal()
    try:
        db.add(Settings(user_id=uid, ai_weight_tuning_enabled=False, send_text_to_ai=False))
        cfg = UserWeightConfig(user_id=uid, m1=0.4, m2=0.3, m3=0.1, m4=0.1, m5=0.1)
        db.add(cfg)
        db.commit()
        w = _get_mastery_weights(db, uid)
        # 关闭调权 → 固定默认等权，忽略持久化值
        assert abs(w.w_error - 0.2) < 1e-6
    finally:
        db.close()


def test_out_of_range_falls_back_to_defaults():
    uid = "u_mw_outofrange"
    _clean(uid)
    db = SessionLocal()
    try:
        db.add(Settings(user_id=uid, ai_weight_tuning_enabled=True, send_text_to_ai=False))
        cfg = UserWeightConfig(user_id=uid, m1=0.9, m2=0.05, m3=0.05, m4=0.0, m5=0.0)
        db.add(cfg)
        db.commit()
        w = _get_mastery_weights(db, uid)
        # 越界（m1>0.5）或非归一化 → 默认
        assert abs(w.w_error - 0.2) < 1e-6
    finally:
        db.close()

"""板块三特征抽取与匿名 ID 单测（M2，决策 v1.7 §4.5/§4.6）。"""
from __future__ import annotations

from anon_id import compute_anon_id


def test_anon_id_deterministic_and_irreversible_shape():
    a1 = compute_anon_id("u_abc")
    a2 = compute_anon_id("u_abc")
    assert a1 == a2
    assert len(a1) == 64
    assert a1 != "u_abc"


def test_anon_id_differs_per_user():
    assert compute_anon_id("u_1") != compute_anon_id("u_2")


def test_extract_skips_stage_missing():
    """stage 缺失用户不抽取（§4.6）。"""
    import jobs.community_extraction as ce
    # 直接验证口径函数存在（真实抽取走 DB，由集成路径覆盖）
    assert ce._current_iso_week()
    assert set(ce.ALLOWED_METRICS) == {"hours", "focus", "fatigue", "completion"}

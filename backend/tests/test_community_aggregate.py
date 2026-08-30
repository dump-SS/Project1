"""板块三聚合计算单测（M3，决策 v1.7 §4.3）。"""
from __future__ import annotations

from community_aggregate import aggregate, build_histogram, percentile


def test_percentile_median():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3.0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_hours_histogram_five_buckets_with_open_top():
    values = [4, 10, 20, 28, 40]  # 覆盖 5 档 + 顶桶开放
    hist = build_histogram(values, "hours")
    # 5 档（含顶桶 open），但因 n=3 合并，实际桶数可能减少
    assert all(b["count"] >= 1 for b in hist)
    # 顶桶 hi 为 None（开放区间）
    top = hist[-1]
    assert top["hi"] is None


def test_small_bucket_merged():
    # 造一个分布：大量在低档，1 个在高档 → 高档桶 count<3 应被并入相邻桶
    values = [1.0] * 20 + [40.0]  # hours：20 个低档 + 1 个高档(>32)
    hist = build_histogram(values, "hours")
    # 所有下发桶 count >= 3 或为唯一桶
    for b in hist:
        assert b["count"] >= 3 or len(hist) == 1


def test_focus_discrete_histogram():
    values = [3, 3, 4, 4, 5]
    hist = build_histogram(values, "focus")
    # 离散值按整数档
    los = [b["lo"] for b in hist]
    assert all(isinstance(lo, int) for lo in los)


def test_aggregate_empty():
    r = aggregate([], "hours")
    assert r["p25"] is None
    assert r["histogram"] == []

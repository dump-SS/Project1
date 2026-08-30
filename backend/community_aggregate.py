"""板块三聚合计算（M3，决策 v1.7 §4.3/§4.9）。

纯函数：给定一批数值（同 metric×stage×period），产出
- 分位数 p25/p50/p75（真值，不对齐桶边界）
- 直方图桶（保守 5 档 + count < n 的桶并入相邻桶）

不落库、不查询，便于单测。
"""
from __future__ import annotations

import math

from config import settings

# 各指标分桶边界（§4.3，配置化思想：边界可改，不改接口形态）
BUCKETS = {
    "hours": [8.0, 16.0, 24.0, 32.0],                 # [0,8) [8,16) [16,24) [24,32) [32,∞)
    "completion": [0.2, 0.4, 0.6, 0.8],               # [0,.2) [.2,.4) [.4,.6) [.6,.8) [.8,1]
    "focus": [1, 2, 3, 4, 5],                          # 离散 1-5 自然分桶（值为整数）
    "fatigue": [1, 2, 3, 4, 5],
}


def percentile(values: list[float], p: float) -> float:
    """线性插值百分位。"""
    if not values:
        raise ValueError("empty values")
    s = sorted(values)
    k = (len(s) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def build_histogram(values: list[float], metric: str) -> list[dict]:
    """保守 5 档直方图 + count < n 桶合并（§4.3）。

    返回 [{lo, hi, count}]，hi 为 None 表示顶桶开放区间；合并后任何桶 count ≥ n。
    """
    n = settings.community_bucket_min
    if metric in ("focus", "fatigue"):
        # 离散 1-5：每值一档；值为整数
        buckets = {}
        for v in values:
            key = int(round(v))
            buckets[key] = buckets.get(key, 0) + 1
        hist = [
            {"lo": k, "hi": k, "count": c}
            for k, c in sorted(buckets.items())
        ]
    else:
        edges = BUCKETS[metric]
        hist = []
        prev_edge = 0.0
        for e in edges:
            cnt = sum(1 for v in values if prev_edge <= v < e)
            hist.append({"lo": prev_edge, "hi": e, "count": cnt})
            prev_edge = e
        # 顶桶 [last, ∞)
        cnt = sum(1 for v in values if v >= edges[-1])
        hist.append({"lo": edges[-1], "hi": None, "count": cnt})

    return _merge_small_buckets(hist, n)


def _merge_small_buckets(hist: list[dict], n: int) -> list[dict]:
    """count < n 的桶并入相邻桶（并入人数更多邻桶，持平并入更低一档）。"""
    # 从后往前合并，避免索引漂移
    result: list[dict] = []
    for b in hist:
        if b["count"] < n:
            if not result:
                result.append(b)
                continue
            # 并入前一个桶
            prev = result[-1]
            prev["count"] += b["count"]
            # hi 扩展（若前桶 hi 是 None 保持开放；否则取当前桶 hi 或保持开放）
            if b["hi"] is None:
                prev["hi"] = None
            else:
                prev["hi"] = max(prev["hi"] or 0, b["hi"] or 0)
        else:
            result.append(dict(b))
    # 若合并后首桶仍 < n 且有多桶，向后并入
    if len(result) > 1 and result[0]["count"] < n:
        result[1]["count"] += result[0]["count"]
        result[1]["lo"] = result[0]["lo"]
        result = result[1:]
    return result


def aggregate(values: list[float], metric: str) -> dict:
    """完整聚合：分位数 + 直方图。"""
    if not values:
        return {"p25": None, "p50": None, "p75": None, "histogram": []}
    return {
        "p25": round(percentile(values, 0.25), 4),
        "p50": round(percentile(values, 0.5), 4),
        "p75": round(percentile(values, 0.75), 4),
        "histogram": build_histogram(values, metric),
    }

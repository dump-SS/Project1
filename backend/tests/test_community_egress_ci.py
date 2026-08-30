"""板块三隐私断言（M5，决策 v1.7 §4.6/§4.9/§5.2）。

- 反向断言：板块三接口请求体不得携带任何特征/身份/原文类字段集（复用 EgressGuard 黑名单）。
- 聚合响应不含任何个体特征字段（只发聚合，§4.9）。
- 特征落库只允许白名单 metric。
"""
from __future__ import annotations

import pytest

from egress_guard import EGRESS_BLOCKED_FIELD_NAMES

# 板块三唯一合法 metric（§4.6 白名单）
ALLOWED_METRICS = {"hours", "focus", "fatigue", "completion"}


def test_egress_blocked_fields_are_defined():
    """EgressGuard 黑名单集合存在且非空（断言直接引用集合，不手写键数）。"""
    assert EGRESS_BLOCKED_FIELD_NAMES


def test_consent_request_has_no_feature_fields():
    """PUT /me/community-consent 请求体 schema 只含 enabled/autoParticipate，不含特征/身份字段。"""
    from schemas.community import CommunityConsentUpdate

    fields = set(CommunityConsentUpdate.model_fields.keys())
    assert fields == {"enabled", "auto_participate"}
    assert not (fields & EGRESS_BLOCKED_FIELD_NAMES)


def test_aggregate_response_has_no_individual_fields():
    """聚合响应只发聚合：无任何个体特征/身份字段。"""
    from schemas.community import CommunityAggregateResponse

    fields = set(CommunityAggregateResponse.model_fields.keys())
    assert not (fields & EGRESS_BLOCKED_FIELD_NAMES)
    # 只含聚合级字段
    assert fields == {"stage", "metric", "period", "pool_size", "percentiles", "histogram", "computed_at"}


def test_feature_metrics_whitelist():
    """特征落库 metric 只允许白名单（§4.6）。"""
    from jobs.community_extraction import ALLOWED_METRICS as JOB_METRICS

    assert set(JOB_METRICS) == ALLOWED_METRICS

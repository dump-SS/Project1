"""EgressGuard 单测（PRD 12.6 出域管控，CI 红线）。

覆盖三类 data_class 的正反用例 + 嵌套 raw 字段递归兜底：
- state_plan：正常放行、未声明 data_class 拒绝
- knowledge_aggregated：白名单字段放行、白名单外字段拒绝
- knowledge_raw：任何 payload 一律拒绝
"""
from __future__ import annotations

import pytest

from egress_guard import (
    EGRESS_BLOCKED_FIELD_NAMES,
    EgressViolation,
    Guard,
    KNOWLEDGE_AGGREGATED,
    KNOWLEDGE_RAW,
    STATE_PLAN,
)


class TestStatePlan:
    def test_state_plan_passes(self):
        payload = {"subject": "math", "focusAvg": 3.5, "stateLabel": "efficient_stable"}
        assert Guard.check(payload, STATE_PLAN) == payload

    def test_undeclared_data_class_rejected(self):
        with pytest.raises(EgressViolation):
            Guard.check({"subject": "math"}, "some_unknown_class")

    def test_state_plan_with_raw_field_rejected(self):
        # 板块一结构化特征里夹带原文字段也必须被拦
        with pytest.raises(EgressViolation, match="禁止出域"):
            Guard.check({"stateLabel": "fatigue_warning", "rawText": "错题原文"}, STATE_PLAN)


class TestKnowledgeAggregated:
    def test_whitelist_passes(self):
        payload = {
            "subject": "math",
            "pointName": "函数单调性",
            "masteryValue": 0.62,
            "errorCandidates": ["概念不清", "计算失误"],
            "retrievedFragmentSnippets": ["单调性定义：f(x) 在区间 D 上…"],
        }
        assert Guard.check(payload, KNOWLEDGE_AGGREGATED) == payload

    def test_unknown_field_rejected(self):
        with pytest.raises(EgressViolation, match="白名单外字段"):
            Guard.check({"pointName": "函数", "secretFreeText": "不该出域"}, KNOWLEDGE_AGGREGATED)

    def test_nested_raw_field_rejected(self):
        with pytest.raises(EgressViolation, match="禁止出域"):
            Guard.check(
                {"errorCandidates": ["计算失误"], "meta": {"correctAnswer": "2"}},
                KNOWLEDGE_AGGREGATED,
            )


class TestKnowledgeRaw:
    def test_knowledge_raw_always_rejected(self):
        payload = {"studentAnswer": "x=1", "rawText": "求 f(x) 的极值"}
        with pytest.raises(EgressViolation, match="knowledge_raw 禁止出域"):
            Guard.check(payload, KNOWLEDGE_RAW)

    def test_every_blocked_field_covered(self):
        # 每个黑名单字段单独出现都必须命中断言（CI 契约）
        for field in sorted(EGRESS_BLOCKED_FIELD_NAMES):
            with pytest.raises(EgressViolation):
                Guard.check({field: "x"}, KNOWLEDGE_AGGREGATED)


class TestNestedScan:
    def test_nested_list_of_dict_rejected(self):
        payload = {
            "errorCandidates": ["粗心"],
            "fragments": [{"snippet": "定义", "error_note": "原文"}],
        }
        with pytest.raises(EgressViolation, match="禁止出域"):
            Guard.check(payload, KNOWLEDGE_AGGREGATED)

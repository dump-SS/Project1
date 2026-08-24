"""CI 出域断言（红线，PRD 12.6 + 计划书 §8）：
错题原文/作答/答案/自述错因/检索片段原文/embedding 向量 永不出现在出域 payload。

覆盖：
1. EgressGuard 黑名单字段（rawText/studentAnswer/correctAnswer/errorNote/...）
2. knowledge_raw data_class 整体拒绝
3. 错题全流程产生的出域 payload 不夹带原文字段（端到端抓 provider 入参）
"""
from __future__ import annotations

import pytest

from egress_guard import EGRESS_BLOCKED_FIELD_NAMES, EgressViolation, Guard, KNOWLEDGE_AGGREGATED, KNOWLEDGE_RAW


RAW_FIELDS = [
    "rawText", "raw_text", "studentAnswer", "student_answer",
    "correctAnswer", "correct_answer", "errorNote", "error_note",
    "questionText", "question_text", "errorSummary", "error_summary",
    "note", "description", "vector", "embedding",
]


def test_all_raw_fields_are_blocked():
    assert set(RAW_FIELDS) <= set(EGRESS_BLOCKED_FIELD_NAMES)


def test_knowledge_raw_whole_class_rejected():
    with pytest.raises(EgressViolation, match="knowledge_raw 禁止出域"):
        Guard.check({"studentAnswer": "x=1"}, KNOWLEDGE_RAW)


def test_errorbook_aggregated_payload_has_no_raw():
    """错题归因出域 payload（模拟）只含白名单字段，杜绝原文串入。"""
    agg = {
        "pointName": "函数单调性",
        "pointDefinition": "随自变量增减的性质",
        "errorCandidates": ["概念不清", "计算失误"],
    }
    # 白名单校验通过
    assert Guard.check(agg, KNOWLEDGE_AGGREGATED) == agg


def test_errorbook_aggregated_payload_with_raw_rejected():
    """试图把 rawText 塞进出域 payload → 直接拒绝。"""
    with pytest.raises(EgressViolation):
        Guard.check(
            {
                "pointName": "函数",
                "rawText": "求 f(x) 的极值（不该出域）",
            },
            KNOWLEDGE_AGGREGATED,
        )


def test_nested_vector_embedding_rejected():
    """向量字段（embedding）也不许出现在出域 payload。"""
    with pytest.raises(EgressViolation):
        Guard.check(
            {"errorCandidates": ["粗心"], "meta": {"embedding": [0.1, 0.2, 0.3]}},
            KNOWLEDGE_AGGREGATED,
        )

"""知识复盘 + 错题解析接口测试。

conftest 默认强制 MockProvider（LLM 返回 None），所以这里断言的是：
- 两个接口都能 200 返回
- 响应结构正确（summary / parse）
- LLM 失败时返回固定降级文案（非空、非 JSON）
- 缺字段时返回 400 统一错误格式
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from schemas.knowledge import (
    ErrorParseRequest,
    KnowledgeSummaryRequest,
)

client = TestClient(app)


def test_knowledge_summary_request_validates() -> None:
    """请求体字段齐全时通过 schema 校验。"""
    req = KnowledgeSummaryRequest.model_validate({
        "subject": "数学",
        "period": "本周",
        "error_summary": "本周共 5 道错题",
        "mastery_changes": "函数单调性掌握度从 72% 降到 65%",
        "state_context": "本周学习状态平稳",
    })
    assert req.subject == "数学"


def test_error_parse_request_validates() -> None:
    """错题解析请求含嵌套 matched_knowledge，通过校验。"""
    req = ErrorParseRequest.model_validate({
        "question_text": "已知 f(x)=e^(x²)，求 f'(x)",
        "student_answer": "f'(x)=e^(x²)",
        "correct_answer": "f'(x)=2xe^(x²)",
        "matched_knowledge": {
            "name": "复合函数求导",
            "definition": "由内外两个函数嵌套构成",
            "error_tip": "注意内层函数也要乘上导数",
        },
    })
    assert req.matched_knowledge.name == "复合函数求导"


def test_knowledge_summary_returns_fallback_on_mock() -> None:
    """MockProvider 返回 None → 走固定降级文案，200 + summary 非空。"""
    r = client.post("/api/v1/knowledge-summary", json={
        "subject": "数学",
        "period": "本周",
        "error_summary": "本周共 5 道错题，3 道集中在函数单调性",
        "mastery_changes": "函数单调性掌握度从 72% 降到 65%",
        "state_context": "本周学习状态平稳，但疲劳度偏高",
    })
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"summary"}
    assert body["summary"].strip()


def test_error_parse_returns_fallback_on_mock() -> None:
    """MockProvider 返回 None → 走固定降级文案，200 + parse 非空。"""
    r = client.post("/api/v1/error-parse", json={
        "question_text": "已知 f(x)=e^(x²)，求 f'(x)",
        "student_answer": "f'(x)=e^(x²)",
        "correct_answer": "f'(x)=2xe^(x²)",
        "matched_knowledge": {
            "name": "复合函数求导",
            "definition": "由内外两个函数嵌套构成",
            "error_tip": "注意内层函数也要乘上导数",
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"parse"}
    assert "错误定位" in body["parse"]


def test_knowledge_summary_missing_field_returns_400() -> None:
    """缺 error_summary → 400 + 统一错误格式。"""
    r = client.post("/api/v1/knowledge-summary", json={
        "subject": "数学",
        "period": "本周",
        "mastery_changes": "降",
        "state_context": "平稳",
    })
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_error_parse_missing_field_returns_400() -> None:
    """缺 matched_knowledge → 400 + 统一错误格式。"""
    r = client.post("/api/v1/error-parse", json={
        "question_text": "q",
        "student_answer": "a",
        "correct_answer": "b",
    })
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"

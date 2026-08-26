"""知识复盘 + 错题归因接口测试（P0 合规整改后）。

conftest 默认强制 MockProvider（LLM 返回 None），所以这里断言：
- 两接口鉴权后 200 返回、响应结构正确
- LLM 失败走固定降级文案（非空）
- 缺字段返回 400 统一错误格式
- 出域合规：请求体不再含错题原文（error-parse 只用 errorId 引用）
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from schemas.knowledge import (
    ErrorParseRequest,
    KnowledgeSummaryCreate,
)

client = TestClient(app)


def test_knowledge_summary_request_validates() -> None:
    """结构化入参通过 schema 校验（无原文字段）。"""
    req = KnowledgeSummaryCreate.model_validate({
        "subject": "SX",
        "period": "本周",
    })
    assert req.subject == "SX"


def test_error_parse_request_validates() -> None:
    """归因请求只引用 errorId，不再含原文。"""
    req = ErrorParseRequest.model_validate({"errorId": "err_0001"})
    assert req.error_id == "err_0001"


def test_knowledge_summary_returns_fallback_on_mock() -> None:
    """MockProvider 返回 None → 走本地降级文案，非空（v2.2 落库后 202）。"""
    r = client.post("/api/v1/knowledge-summary", json={
        "subject": "SX",
        "period": "本周",
    })
    assert r.status_code == 202
    body = r.json()
    assert set(body.keys()) == {"summary"}
    assert body["summary"].strip()


def test_error_parse_returns_fallback_on_mock() -> None:
    """MockProvider 返回 None → 走本地降级文案（通用兜底，非函数特化）。"""
    r = client.post("/api/v1/error-parse", json={"errorId": "err_0001"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"parse"}
    assert "错误定位" in body["parse"]


def test_knowledge_summary_missing_field_returns_400() -> None:
    """缺 period → 400 + 统一错误格式。"""
    r = client.post("/api/v1/knowledge-summary", json={"subject": "SX"})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_error_parse_missing_field_returns_400() -> None:
    """缺 errorId → 400 + 统一错误格式。"""
    r = client.post("/api/v1/error-parse", json={})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_error_parse_rejects_raw_text_payload() -> None:
    """合规断言：原文字段不再被契约接受（P0 整改产物）。"""
    r = client.post("/api/v1/error-parse", json={
        "question_text": "已知 f(x)=e^(x²)，求 f'(x)",
        "student_answer": "f'(x)=e^(x²)",
    })
    assert r.status_code == 400

"""CI 出域断言（红线，PRD 12.6 + 计划书 §8）：
错题原文/作答/答案/自述错因/检索片段原文/embedding 向量 永不出现在出域 payload。

覆盖：
1. EgressGuard 黑名单字段（rawText/studentAnswer/correctAnswer/errorNote/...）
2. knowledge_raw data_class 整体拒绝
3. 错题全流程产生的出域 payload 不夹带原文字段（端到端抓 provider 入参）
4. **embedding 侧出域**：用户内容的 embed_text 调用点必须显式声明
   ``source=EMBED_SRC_USER``；漏声明就可能被当成知识库出域。
   本条用 AST 静态扫描源码，**新增调用点忘标会直接挂 CI**。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from egress_guard import EGRESS_BLOCKED_FIELD_NAMES, EgressViolation, Guard, KNOWLEDGE_AGGREGATED, KNOWLEDGE_RAW

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTES_DIR = BACKEND_ROOT / "routes"


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


# ---------------------------------------------------------------------------
# embedding 侧：错题原文永不出域（M3 验收门）
# ---------------------------------------------------------------------------

# 允许省略 source 的白名单：只有知识库链路可以。
# 理由：知识库内容是编者提供的公开数据，出域是既定决策；且现网知识库索引由外部
# 模型（EMBED_MODEL=embedding-3，1024 维）建成，与本地 bge（512 维）**不在同一
# 向量空间**，强行改本地会让召回彻底失效。错题/学习记录则**必须**显式标注。
_KB_ONLY_OK = {"knowledge_kb.py"}


def _read(path: pathlib.Path) -> str:
    # utf-8-sig：部分 routes 文件带 BOM，ast.parse 不接受 U+FEFF，但 import 机制吃得下。
    return path.read_bytes().decode("utf-8-sig")


def _embed_text_calls() -> list[tuple[str, int, bool]]:
    """扫 routes/ 下所有 embed_text(...) 调用点 → (文件, 行号, 是否显式标 source)。"""
    found: list[tuple[str, int, bool]] = []
    for path in sorted(ROUTES_DIR.glob("*.py")):
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "embed_text"):
                continue
            has_source = any(kw.arg == "source" for kw in node.keywords)
            found.append((path.name, node.lineno, has_source))
    return found


def test_embed_text_call_sites_exist():
    """防扫描器自身失效：调用点集合不该是空的。"""
    assert _embed_text_calls(), "routes/ 下没扫到 embed_text 调用——扫描逻辑坏了"


def test_user_content_embed_calls_declare_source():
    """🔴 除知识库链路外，所有 embed_text 调用点必须显式声明 source。"""
    offenders = [
        f"{name}:{line}"
        for name, line, has_source in _embed_text_calls()
        if not has_source and name not in _KB_ONLY_OK
    ]
    assert not offenders, (
        "这些 embed_text 调用点没声明 source，可能把用户内容按知识库出域："
        + "、".join(offenders)
    )


def test_error_book_call_site_is_user_scope():
    """错题本写入侧必须声明 EMBED_SRC_USER。"""
    tree = ast.parse(_read(ROUTES_DIR / "error_book.py"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "embed_text"):
            continue
        src = next((kw.value for kw in node.keywords if kw.arg == "source"), None)
        assert isinstance(src, ast.Name) and src.id == "EMBED_SRC_USER", (
            f"error_book.py:{node.lineno} 的 embed_text 未使用 EMBED_SRC_USER"
        )

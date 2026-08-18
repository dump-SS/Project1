"""知识复盘 + 错题解析（PRD v1.4 板块二）。

两个接口都用 LLM 生成文案，复用 llm_provider 的 get_provider()：
- 超时 / 重试 / 降级都靠 provider 已有机制（60s 超时 + 内置重试 1 次 + 失败返回 None）
- LLM 失败（返回 None 或抛异常）时返回固定降级文案，前端永远拿得到内容

公开接口：不加 current_user，纯工具型「入参文本 → 出参文案」。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, status

from llm_provider import get_provider
from schemas.knowledge import (
    ErrorParseRequest,
    ErrorParseResponse,
    KnowledgeSummaryRequest,
    KnowledgeSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["知识复盘"])

# --- 知识复盘 prompt ---

KNOWLEDGE_SUMMARY_SYSTEM = """你是一个学科分析助手，角色类似于特级教师给学生写周度学习复盘。
你需要根据学生本周的错题摘要、知识点掌握度变化和整体学习状态，生成一段 150 字以内的知识复盘。

输出结构（严格按此顺序，用换行分隔）：
1. 概览（一句话总结本周学科表现）
2. 薄弱点分析（指出具体知识点和出错原因）
3. 改进建议（1-2 条具体可执行的行动）
4. 鼓励收尾（一句温暖的话）

风格要求：
- 专业但不晦涩，像老师面对面点评
- 不用"您"，用"你"
- 不诊断心理，不评价人格，只说学习内容
- 禁止出现"建议就医""建议咨询心理医生"等表述
- 纯文本输出，不要 JSON，不要 markdown 代码块"""

KNOWLEDGE_SUMMARY_FALLBACK = (
    "本周你在函数单调性上遇到了一些挑战，特别是复合函数判定步骤容易出错。"
    "建议回顾一下复合函数的定义，再针对性做 3-5 道基础题巩固。"
    "错题是进步的阶梯，每一道都在帮你找到知识的盲区 🌱"
)


def _build_knowledge_summary_user(payload: KnowledgeSummaryRequest) -> str:
    """把请求体四个字段拼成一段话喂给 LLM（任务文档约定）。"""
    return (
        f"学科：{payload.subject}\n"
        f"周期：{payload.period}\n"
        f"错题摘要：{payload.error_summary}\n"
        f"掌握度变化：{payload.mastery_changes}\n"
        f"学习状态：{payload.state_context}"
    )


@router.post(
    "/knowledge-summary",
    response_model=KnowledgeSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="学科知识复盘（LLM 生成）",
)
def create_knowledge_summary(payload: KnowledgeSummaryRequest) -> KnowledgeSummaryResponse:
    """LLM 生成知识复盘；失败时返回固定降级文案。"""
    user_prompt = _build_knowledge_summary_user(payload)

    text: str | None = None
    try:
        provider = get_provider()
        text = provider.generate(user_prompt, context={"system": KNOWLEDGE_SUMMARY_SYSTEM})
    except Exception as e:  # noqa: BLE001 — 任何 LLM 异常都降级
        logger.warning("[KNOWLEDGE_SUMMARY] LLM 调用异常: %s: %s", type(e).__name__, e)

    if not text or not text.strip():
        logger.info("[KNOWLEDGE_SUMMARY] LLM 未返回文本，走降级文案")
        return KnowledgeSummaryResponse(summary=KNOWLEDGE_SUMMARY_FALLBACK)

    return KnowledgeSummaryResponse(summary=text.strip())


# --- 错题解析 prompt ---

ERROR_PARSE_SYSTEM = """你是一个高中学科智能辅导助手。学生提交了一道错题，你需要结合题目内容、学生的错误作答、正确答案，以及关联的知识点信息，生成一段解析。

输出格式（严格按此顺序，用 markdown）：

### 📌 错误定位
一句话指出学生错在哪一步、为什么错。

### 💡 正确解法
写出完整的解题步骤（3-5步），每步一行。

### 🔗 关联知识点
用一句话解释这道题用到的核心知识点（引用传入的知识点定义），并提醒易错点。

### ✅ 同类题建议
给出 1 条练习建议（比如"再找 2 道复合函数求导题，重点检查内层导数是否乘上"）。

风格要求：
- 像特级教师在批改作业，语气温和但准确
- 不用"您"，用"你"
- 步骤清晰，用数字编号
- 不超过 300 字"""

ERROR_PARSE_FALLBACK = (
    "### 📌 错误定位\n"
    "看起来你在求导时漏掉了内层函数的导数乘法。\n\n"
    "### 💡 正确解法\n"
    "1. 识别外层函数 e^u 和内层函数 u=x²\n"
    "2. 外层导数 e^u 保持不变\n"
    "3. 内层导数 2x\n"
    "4. 相乘得到 2xe^(x²)\n\n"
    "### 🔗 关联知识点\n"
    "复合函数求导遵循链式法则，不要忘记乘内层导数。\n\n"
    "### ✅ 同类题建议\n"
    "再练 2 道复合函数求导，重点检查内层导数是否乘上 🌱"
)


def _build_error_parse_user(payload: ErrorParseRequest) -> str:
    """把题目、作答、正确答案、匹配知识点拼成一段话喂给 LLM。"""
    k = payload.matched_knowledge
    return (
        f"题目：{payload.question_text}\n"
        f"学生作答：{payload.student_answer}\n"
        f"正确答案：{payload.correct_answer}\n"
        f"关联知识点：\n"
        f"- 名称：{k.name}\n"
        f"- 定义：{k.definition}\n"
        f"- 易错点：{k.error_tip}"
    )


@router.post(
    "/error-parse",
    response_model=ErrorParseResponse,
    status_code=status.HTTP_200_OK,
    summary="错题智能解析（LLM 生成）",
)
def create_error_parse(payload: ErrorParseRequest) -> ErrorParseResponse:
    """LLM 生成错题解析；失败时返回固定降级文案。"""
    user_prompt = _build_error_parse_user(payload)

    text: str | None = None
    try:
        provider = get_provider()
        text = provider.generate(user_prompt, context={"system": ERROR_PARSE_SYSTEM})
    except Exception as e:  # noqa: BLE001 — 任何 LLM 异常都降级
        logger.warning("[ERROR_PARSE] LLM 调用异常: %s: %s", type(e).__name__, e)

    if not text or not text.strip():
        logger.info("[ERROR_PARSE] LLM 未返回文本，走降级文案")
        return ErrorParseResponse(parse=ERROR_PARSE_FALLBACK)

    return ErrorParseResponse(parse=text.strip())

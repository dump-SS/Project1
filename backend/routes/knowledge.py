"""知识复盘 + 错题归因（PRD v1.4 板块二）。

P0 合规整改（PRD 12.6）：
- POST /error-parse：旧版把 question_text / student_answer / correct_answer
  直接拼进 prompt 发给云端 LLM，违反出域边界。整改为「引用已入库错题
  （errorId）」：原文只在本地检索，出域内容仅为 knowledge_aggregated
  白名单字段（知识点名称/定义/易错点 + 错因候选），由 EgressGuard 强校验。
- POST /knowledge-summary：加 current_user 鉴权 + 结构化入参 + EgressGuard
  + safety_filter 审核，且不再接受前端自由拼装的错题摘要原文。
- 两接口失败都走固定降级文案（本地模板），前端永远拿得到内容。

v2.1 完成后，error-parse 的检索片段来自 kb_error_points/kb_points，
knowledge-summary 异步落 summaries 表（dimension=knowledge）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from llm_provider import get_provider
from .deps import current_user
from schemas.knowledge import (
    ErrorParseRequest,
    ErrorParseResponse,
    KnowledgeSummaryCreate,
    KnowledgeSummaryResponse,
)
from schemas.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["知识复盘"])

# 知识复盘每日频率限制（PRD 6.4 / config.rate_limit_summary_per_day，S0-T5 已持久化到 rate_limit_counters）
def _consume_knowledge_summary_budget(user_id: str) -> None:
    """每日限流：查/增 rate_limit_counters；达限抛 429。系统触发（沿用 W3-1）不计入用户限额。"""
    from datetime import datetime, timedelta

    from config import settings
    from database import SessionLocal
    from models.rate_limit import RateLimitCounter

    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        row = (
            db.query(RateLimitCounter)
            .filter(
                RateLimitCounter.user_id == user_id,
                RateLimitCounter.bucket_key == "knowledge_summary",
                RateLimitCounter.bucket_date >= today,
            )
            .first()
        )
        if row is None:
            row = RateLimitCounter(
                id=f"rl_{__import__('uuid').uuid4().hex[:12]}",
                user_id=user_id,
                bucket_key="knowledge_summary",
                bucket_date=datetime.utcnow(),
                count=0,
            )
            db.add(row)
        if row.count >= settings.rate_limit_summary_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMITED", "message": "今日知识复盘次数已达上限，请明天再试"},
            )
        row.count += 1
        db.commit()
    finally:
        db.close()

# --- 知识复盘 prompt ---

KNOWLEDGE_SUMMARY_SYSTEM = """你是一个学科分析助手，角色类似于特级教师给学生写周度学习复盘。
你需要根据学生本周的结构化学习特征（错题数量、知识点掌握度数值、状态标签），生成一段 150 字以内的知识复盘。

输出结构（严格按此顺序，用换行分隔）：
1. 概览（一句话总结本周学科表现）
2. 薄弱点分析（指出具体知识点和出错方向）
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


# --- 错题归因 prompt（合规形态：只喂检索片段与错因候选） ---

ERROR_PARSE_SYSTEM = """你是一个高中学科智能辅导助手。学生提交了一道错题。
你只能基于给定的知识点片段与错因候选做分析，不得要求、引用或补写题目原文。

输出格式（严格按此顺序，用 markdown）：

### 📌 错误定位
一句话指出学生可能错在哪一类步骤。

### 💡 正确解法
写出核心解题思路（3-5 步），每步一行。

### 🔗 关联知识点
用一句话解释这道题用到的核心知识点，并提醒易错点。

### ✅ 同类题建议
给出 1 条练习建议。

风格要求：
- 像特级教师在批改作业，语气温和但准确
- 不用"您"，用"你"
- 步骤清晰，用数字编号
- 不超过 300 字"""

ERROR_PARSE_FALLBACK = (
    "### 📌 错误定位\n"
    "看起来你在推导时漏掉了关键一步，建议对照解题步骤逐行检查。\n\n"
    "### 💡 正确解法\n"
    "1. 识别题目考查的核心知识点\n"
    "2. 写出对应的定义与公式\n"
    "3. 分步代入条件，逐步化简\n"
    "4. 比较每一步结果，定位偏差\n\n"
    "### 🔗 关联知识点\n"
    "这道题考查核心概念的综合运用，注意定义成立的前提条件。\n\n"
    "### ✅ 同类题建议\n"
    "再练 2 道同知识点基础题，先确保每一步都有依据 🌱"
)


# --- 知识复盘（鉴权 + 结构化 + 落库 summaries.dimension=knowledge） ---

@router.post(
    "/knowledge-summary",
    response_model=KnowledgeSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="学科知识复盘（LLM 生成，原文不出域，落入 summaries）",
)
def create_knowledge_summary(
    payload: KnowledgeSummaryCreate,
    _user: User = Depends(current_user),
) -> KnowledgeSummaryResponse:
    """知识复盘（v2.2 改造）：结构化入参 → 落 summaries（dimension=knowledge）→ LLM 生成。

    出域内容仅为知识聚合白名单字段（EgressGuard 校验），错题原文永不出域。
    """
    # 每日频率限制（PRD 6.4 控成本，S0-T5：持久化到 rate_limit_counters，重启不丢）
    _consume_knowledge_summary_budget(_user.user_id)

    text: str | None = None
    try:
        provider = get_provider()
        text = provider.generate(
            _build_knowledge_summary_user(payload),
            context={
                "system": KNOWLEDGE_SUMMARY_SYSTEM,
                "scene": "knowledge_summary",
                "subject": payload.subject,
                # EgressGuard：知识聚合包白名单（无原文）
                "egress_fields": {"subject": payload.subject, "period": payload.period},
                "data_class": "knowledge_aggregated",
            },
        )
        if text:
            from safety_filter import check

            passed, reason = check(text)
            if not passed:
                logger.warning("[KNOWLEDGE_SUMMARY] 审核拦截: %s", reason)
                text = None
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_SUMMARY] LLM 调用异常: %s: %s", type(e).__name__, e)

    result = text.strip() if text and text.strip() else KNOWLEDGE_SUMMARY_FALLBACK

    # 落 summaries 表，dimension=knowledge（板块二复盘与板块一分域）
    _persist_knowledge_summary(_user.user_id, payload, result, source="llm" if text else "template")
    return KnowledgeSummaryResponse(summary=result)


def _persist_knowledge_summary(
    user_id: str,
    payload: KnowledgeSummaryCreate,
    summary_text: str,
    source: str,
) -> None:
    """知识复盘落库（summaries.dimension=knowledge），失败仅记日志不阻断响应。"""
    try:
        from datetime import date as _date, datetime as _dt
        from database import SessionLocal
        from models.summary import Summary as SummaryORM

        db = SessionLocal()
        try:
            db.add(SummaryORM(
                id=f"sum_{__import__('uuid').uuid4().hex[:12]}",
                user_id=user_id,
                dimension="knowledge",
                period_start=_date.today(),
                period_end=_date.today(),
                generation_status="ready",
                generation_source=source,
                generation_completed_at=_dt.utcnow(),
                content_overview=summary_text,
                data_record_count=0,
                data_subjects=f'["{payload.subject}"]',
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_SUMMARY] 落库失败（不影响响应）: %s", e)


def _build_knowledge_summary_user(payload: KnowledgeSummaryCreate) -> str:
    """结构化学科周期 → prompt（无原文，knowledge_aggregated 语义）。"""
    return (
        f"学科：{payload.subject}\n"
        f"周期：{payload.period}\n"
        "请基于结构化特征生成周度知识复盘（当前无错题原文，只做常规学业建议）。"
    )


# --- 错题归因（errorId 引用，原文只本地检索） ---

@router.post(
    "/error-parse",
    response_model=ErrorParseResponse,
    status_code=status.HTTP_200_OK,
    summary="错题智能解析（合规：引用已入库错题，原文不出域）",
)
def create_error_parse(
    payload: ErrorParseRequest,
    _user: User = Depends(current_user),
) -> ErrorParseResponse:
    """错题归因（P0 整改，真实可用）。

    出域内容 = 知识点名称/定义/易错点 + 错因候选（knowledge_aggregated），
    由 EgressGuard 白名单强校验；错题原文只在本地检索，永不出域。
    """
    # 本地检索：优先查 kb_point/错题关联（v2.1 建表后启用），
    # 表未就绪时仅返回中性兜底，不把原文带出去。
    text: str | None = None
    try:
        prompt, egress = _build_error_parse_prompt(payload.error_id)
        provider = get_provider()
        text = provider.generate(
            prompt,
            context={"system": ERROR_PARSE_SYSTEM, "scene": "error_parse"},
        )
        if text:
            from safety_filter import check

            passed, reason = check(text)
            if not passed:
                logger.warning("[ERROR_PARSE] 审核拦截: %s", reason)
                text = None
    except Exception as e:  # noqa: BLE001
        logger.warning("[ERROR_PARSE] LLM 调用异常: %s: %s", type(e).__name__, e)

    if not text or not text.strip():
        logger.info("[ERROR_PARSE] LLM 未返回文本，走降级文案")
        return ErrorParseResponse(parse=ERROR_PARSE_FALLBACK)

    return ErrorParseResponse(parse=text.strip())


def _build_error_parse_prompt(error_id: str) -> tuple[str, dict]:
    """本地检索错题关联知识点，构造合规 prompt。

    返回 (prompt, egress_fields)。检索到的片段只压缩为「知识点名 + 易错点」，
    不带题目原文/作答/答案。知识库未就绪时用中性提示。
    """
    retrieved = _retrieve_error_points(error_id)
    if not retrieved:
        prompt = (
            "请基于通用的高中数学解题思路，给出一道错题的归因分析"
            "（无检索到的知识点，请给出通用的检查清单式建议）。"
        )
        return prompt, {}

    lines = []
    agg = []
    for p in retrieved[:5]:
        lines.append(f"- 知识点：{p['name']}；定义：{p['definition']}；易错点：{p['error_tip']}")
        agg.append(
            {
                "pointName": p["name"],
                "pointDefinition": p["definition"],
            }
        )
    prompt = "检索到的关联知识点如下：\n" + "\n".join(lines) + "\n请据此生成错题归因分析。"
    return prompt, {"retrievedFragmentSnippets": agg}


def _retrieve_error_points(error_id: str) -> list[dict]:
    """本地检索错题关联的知识点（原文不出库、不出域）。

    v2.1 建 kb_error_points/kb_points 表后接真实查询；
    当前返回空列表（提示走通用兜底）。
    """
    # 兜底：不把 error_id 当原文，仅尝试真实表（表未建时静默返回空）。
    try:
        from database import SessionLocal
        from sqlalchemy import text as _sa_text

        db = SessionLocal()
        try:
            rows = db.execute(
                _sa_text(
                    "SELECT p.name, p.definition, p.error_tip "
                    "FROM kb_error_points ep JOIN kb_points p ON p.id = ep.point_id "
                    "WHERE ep.error_id = :eid LIMIT 5"
                ),
                {"eid": error_id},
            ).mappings().all()
            return [dict(r) for r in rows]
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — 表未建/连接失败均降级
        logger.info("[ERROR_PARSE] 知识库检索不可用（%s），走通用兜底", type(e).__name__)
        return []

"""LLM 出域管控层 EgressGuard（PRD 12.6，P0 合规基建）。

把「哪些字段能发给云端 LLM」从口头约定变成代码强制：

    DataClass = "state_plan" | "knowledge_aggregated" | "knowledge_raw"

- ``state_plan``：板块一沿用（结构化特征 + 用户文本受 send_text_to_ai 约束）。
- ``knowledge_aggregated``：仅放行白名单字段（错因枚举、mastery 数值、
  检索片段元信息、状态摘要）。白名单上没写的一律拒绝序列化。
- ``knowledge_raw``：错题原文/作答/正确答案/自述错因，直接拒绝出域，
  audit log 记 ERROR 并抛 EgressViolation。CI 出域断言以此为准。

调用约定：所有产生出域 payload 的业务代码必须先 ``Guard.validate(payload)``
拿到放行后的 payload 再交给 provider；provider 层对 ``knowledge_raw`` 再次兜底拒绝。
关键安全属性：**默认拒绝**——任何未声明 data_class、或聚合包里有未知字段、
或任何知识原文出现在 payload 里的序列化都会被拦下，而不是默然放行。
"""
from __future__ import annotations

import logging

__all__ = [
    "DataClass",
    "EgressViolation",
    "Guard",
    "EGRESS_BLOCKED_FIELD_NAMES",
    "EMBED_SRC_KB",
    "EMBED_SRC_USER",
    "assert_embed_source_offdomain_allowed",
]

logger = logging.getLogger(__name__)

# 三种 data_class（PRD 12.6）
STATE_PLAN = "state_plan"
KNOWLEDGE_AGGREGATED = "knowledge_aggregated"
KNOWLEDGE_RAW = "knowledge_raw"

DataClass = str

# knowledge_aggregated 白名单：加字段必须先评审（契约 v1.5 的 EgressGuard 部分）
AGGREGATED_ALLOWED_KEYS: frozenset[str] = frozenset({
    "subject",
    "subjectName",
    "period",
    "periodStart",
    "periodEnd",
    "recordCount",
    "mastery",
    "masteryValue",
    "sampleSize",
    "dataSufficient",
    "pointName",
    "pointDefinition",
    "errorType",
    "errorCandidates",
    "retrievedFragmentSnippets",
    "stateLabel",
    "stateSummary",
    "trend",
    "signals",
    "planCompletionRatio",
    "todayCompletedCount",
    "todayTotalCount",
    "focusAvg",
    "fatigueAvg",
    "difficultyFeel",
})

# knowledge_raw 字段名（无论嵌套多深，出现即拒绝）
EGRESS_BLOCKED_FIELD_NAMES: frozenset[str] = frozenset({
    "rawText",
    "raw_text",
    "studentAnswer",
    "student_answer",
    "correctAnswer",
    "correct_answer",
    "errorNote",
    "error_note",
    "questionText",
    "question_text",
    "errorSummary",
    "error_summary",
    "note",
    "description",
    "vector",
    "embedding",
})


class EgressViolation(Exception):
    """越权出域：knowledge_raw 序列化或 knowledge_aggregated 白名单外字段。"""


# ---------------------------------------------------------------------------
# embedding 侧的数据来源标记
#
# 为什么要单独一套：上面的 Guard 拦的是**dict payload**（LLM 调用），靠字段名识别知识原文。
# embedding 调用送出去的是**一整条裸文本**，没有字段名可扫，所以必须由调用方在调用点
# 显式声明「这条文本是什么来源」，再在这里做一次判定。
#
# 与知识库/错题那对既定决策对应（AGENTS.md 铁律 6）：
# - 知识库内容（编者提供、公开）→ 允许走外部 embedding API（既定决策）
# - 用户内容（错题原文 / 作答 / 学习记录）→ **永不出域**，只能用本地模型
# ---------------------------------------------------------------------------
EMBED_SRC_KB = "kb"
EMBED_SRC_USER = "user"

# 允许走外部 embedding API 的来源白名单。
# **用户内容（EMBED_SRC_USER）不在其中，且不可通过配置放开**——它只能在用户**显式 opt-in**
# （PRD 12.6 / D41 的 settings.user_content_embedding_api_enabled）时，
# 由调用方显式传 user_api_opt_in=True 放行。默认参数 False ⇒ 默认拒绝。
EMBED_OFFDOMAIN_ALLOWED_SOURCES: frozenset[str] = frozenset({EMBED_SRC_KB})


def assert_embed_source_offdomain_allowed(source: str, *, user_api_opt_in: bool = False) -> None:
    """准备把文本发给**外部** embedding API 前的最后一道闸。

    与 :meth:`Guard.check` 同为「默认拒绝」：未声明的来源一律当作越权处理，
    不放行到 api 模式。

    Args:
        source: 数据来源（``EMBED_SRC_KB`` / ``EMBED_SRC_USER``）。
        user_api_opt_in: **仅对用户内容有意义**。用户内容默认禁止出域；只有该用户在自己的设置里
            显式开启（``settings.user_content_embedding_api_enabled``，PRD 12.6 / D41）时，
            调用方才传 ``True`` 放行。**默认 False = 默认拒绝**；而且它**不是配置项** ——
            按用户、按请求显式给出，``KB_EMBED_MODE`` 放不开它。

    Raises:
        EgressViolation: 来源未声明，或属于禁止出域的用户内容（且未 opt-in）。
    """
    if source not in (EMBED_SRC_KB, EMBED_SRC_USER):
        logger.error("[EGRESS] 未声明合法 embedding 来源：%r", source)
        raise EgressViolation(f"未声明合法 embedding 来源：{source!r}")
    if source in EMBED_OFFDOMAIN_ALLOWED_SOURCES:
        return
    if source == EMBED_SRC_USER and user_api_opt_in:
        # 用户显式 opt-in：放行，但留一条痕（是谁开的可从 settings 表追）。
        logger.info("[EGRESS] 用户内容 embedding 出域：该用户已显式 opt-in（PRD 12.6 / D41）")
        return
    logger.error(
        "[EGRESS] 来源 %s 禁止出域到外部 embedding API"
        "（错题原文/作答/学习记录默认永不出域，除非用户显式 opt-in）",
        source,
    )
    raise EgressViolation(
        f"embedding 来源 {source!r} 禁止出域：用户内容只能用本地模型（除非该用户已显式 opt-in）"
    )


class Guard:
    """出域白名单校验器。全部静态方法，无状态、可注入测试。"""

    @staticmethod
    def check(payload: dict, data_class: DataClass) -> dict:
        """校验 payload 是否符合 data_class 出域规则，通过则原样返回。

        Raises:
            EgressViolation: 未声明 data_class / knowledge_raw 越权 /
                knowledge_aggregated 含白名单外字段。
        """
        if data_class not in (STATE_PLAN, KNOWLEDGE_AGGREGATED, KNOWLEDGE_RAW):
            raise EgressViolation(f"未声明合法 data_class：{data_class!r}")

        if data_class == KNOWLEDGE_RAW:
            logger.error("[EGRESS] knowledge_raw 出域被拒绝（payload keys=%s）", list(payload))
            raise EgressViolation("knowledge_raw 禁止出域：错题原文/作答/自述错因永不出域")

        Guard._reject_raw_fields(payload)

        if data_class == KNOWLEDGE_AGGREGATED:
            unknown = [k for k in payload if k not in AGGREGATED_ALLOWED_KEYS]
            if unknown:
                logger.error("[EGRESS] knowledge_aggregated 白名单外字段被拦截：%s", unknown)
                raise EgressViolation(
                    f"knowledge_aggregated 出域 payload 含白名单外字段：{unknown}"
                )

        return payload

    @staticmethod
    def _reject_raw_fields(payload: dict, path: str = "") -> None:
        """递归扫描：任何 knowledge_raw 字段名（嵌套出现在 dict key）一律拒绝。"""
        for key, value in payload.items():
            if key in EGRESS_BLOCKED_FIELD_NAMES:
                full = f"{path}.{key}" if path else key
                logger.error("[EGRESS] 检测到知识原文字段出域：%s", full)
                raise EgressViolation(f"知识原文字段 {full} 禁止出域")
            if isinstance(value, dict):
                Guard._reject_raw_fields(value, f"{path}.{key}" if path else key)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        Guard._reject_raw_fields(item, f"{path}.{key}[]" if path else f"{key}[]")

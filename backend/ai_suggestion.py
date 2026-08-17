"""AI 建议生成编排层（PRD 5.3 / 5.4）。

职责：组装上下文 → 调 LLM provider → 安全审核 → 失败走兜底 → 写回 ORM。
不含公式计算（在 state_engine），不含 HTTP 逻辑（在 routes）。

MVP 用同步生成：POST 请求内跑完，前端轮询拿到终态。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from llm_provider import get_provider
from models.learning_record import LearningRecord
from models.assessment import AssessmentSnapshot
from models.recommendation import Recommendation
from models.summary import Summary
from safety_filter import check, is_crisis_signal, CRISIS_RESPONSE
from state_calculator import compute_window_for_records, orm_record_to_engine_input
from template_fallback import build_template_recommendation

logger = logging.getLogger(__name__)

MIN_RECORDS_FOR_SUMMARY = 5  # PRD 5.4：数据不足时不硬凑


def generate_recommendation(
    db: Session,
    rec_id: str,
    user_id: str,
    scene: str,
    subject: str | None,
    record_id: str | None,
    trigger_record_row: LearningRecord | None = None,
) -> None:
    """生成单次学习建议（PRD 5.3）。

    在 POST /learning-records 或 POST /recommendations 时调用。
    流程：读窗口 → 组装上下文 → LLM → 安全审核 → 失败走模板兜底 → 写回 ORM。
    建议任何情况下都给得出内容（PRD 5.3 / 验收标准）。
    """
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        logger.error("[AI] Recommendation %s 不存在", rec_id)
        return

    subj = subject or trigger_record_row.subject if trigger_record_row else subject or "other"

    # 读窗口（最近 7 条），拿状态标签和信号
    rows = _window_rows(db, user_id, subj)
    state_label = "insufficient_data"
    plan_completion_ratio = None
    record_focus = trigger_record_row.self_report_focus if trigger_record_row else None
    record_fatigue = trigger_record_row.self_report_fatigue if trigger_record_row else None
    assessment_id = None

    if rows:
        engine_inputs = [orm_record_to_engine_input(r) for r in rows]
        window = compute_window_for_records(engine_inputs)
        state_label = window.state_label.value
        assessment_id = rec.based_on_assessment_id

    # 危机信号检查（PRD 6.3）：不过 LLM，直接走硬编码文案
    if trigger_record_row and is_crisis_signal(
        f"{trigger_record_row.self_report_emotion} {trigger_record_row.note or ''}"
    ):
        items = [{"title": "关心一下你的状态", "content": CRISIS_RESPONSE}]
        _finalize_recommendation(db, rec, items, "template", state_label, assessment_id, record_id,
                                  "检测到可能的危机信号，切换为审定文案")
        return

    # 尝试 LLM 生成
    provider = get_provider()
    prompt = _build_recommendation_prompt(subj, state_label, record_focus, record_fatigue, plan_completion_ratio)
    llm_text = provider.generate(prompt, {"scene": scene, "subject": subj})

    if llm_text:
        # 安全审核
        passed, reason = check(llm_text)
        if passed:
            items = _parse_llm_items(llm_text)
            if items:
                _finalize_recommendation(db, rec, items, "llm", state_label, assessment_id, record_id,
                                          f"LLM 生成，依据{subj}状态（{state_label}）")
                return
        else:
            logger.warning("[AI] 建议 LLM 内容被安全审核拦截: %s", reason)

    # 兜底：规则模板
    items, explain = build_template_recommendation(
        state_label, subj, record_focus, record_fatigue, plan_completion_ratio
    )
    _finalize_recommendation(db, rec, items, "template", state_label, assessment_id, record_id, explain)


def generate_summary(
    db: Session,
    summary_id: str,
    user_id: str,
    period_start,
    period_end,
) -> None:
    """生成周期复盘（PRD 5.4）。

    复盘不做模板兜底：LLM 失败即 failed，数据不足即 insufficient_data。
    """
    summ = db.get(Summary, summary_id)
    if summ is None:
        logger.error("[AI] Summary %s 不存在", summary_id)
        return

    # 拉区间内记录
    rows = db.execute(
        select(LearningRecord).where(
            LearningRecord.user_id == user_id,
            LearningRecord.started_at >= period_start,
            LearningRecord.started_at <= period_end,
        ).order_by(LearningRecord.started_at.asc())
    ).scalars().all()

    record_count = len(rows)

    # 数据不足
    if record_count < MIN_RECORDS_FOR_SUMMARY:
        summ.generation_status = "insufficient_data"
        summ.generation_completed_at = datetime.utcnow()
        summ.data_record_count = record_count
        summ.data_min_required = MIN_RECORDS_FOR_SUMMARY
        summ.message = "本周记录较少，暂不生成完整复盘"
        db.commit()
        logger.info("[AI] 复盘 %s 数据不足（%d < %d）", summary_id, record_count, MIN_RECORDS_FOR_SUMMARY)
        return

    # 组装 dataPoints
    subjects = sorted(set(r.subject for r in rows))
    snap_rows = db.execute(
        select(AssessmentSnapshot).where(
            AssessmentSnapshot.user_id == user_id,
            AssessmentSnapshot.subject.in_(subjects),
        ).order_by(AssessmentSnapshot.computed_at.asc())
    ).scalars().all()
    state_labels = [s.state_label for s in snap_rows if s.data_sufficient]
    referenced_ids = [s.id for s in snap_rows]
    plan_completion_ratio = _compute_plan_completion(db, user_id)

    # 尝试 LLM 生成
    provider = get_provider()
    prompt = _build_summary_prompt(rows, snap_rows, plan_completion_ratio)
    llm_text = provider.generate(prompt, {"period": f"{period_start}~{period_end}"})

    if llm_text:
        passed, reason = check(llm_text)
        if passed:
            content = _parse_llm_summary(llm_text)
            if content:
                _finalize_summary(db, summ, content, "llm", record_count, subjects,
                                  plan_completion_ratio, referenced_ids)
                return
        else:
            logger.warning("[AI] 复盘 LLM 内容被安全审核拦截: %s", reason)

    # 复盘严格不做模板兜底（PRD 5.4 / 契约 GenerationStatus 互斥约束）。
    # 即使 MockProvider 返回 None，也必须 failed，不能伪造 source=template 的完整复盘。
    summ.generation_status = "failed"
    summ.generation_completed_at = datetime.utcnow()
    summ.message = "生成失败，请稍后再试"
    db.commit()
    logger.warning("[AI] 复盘 %s LLM 生成失败或不可用，标记 failed", summary_id)


# ---------- 内部工具 ----------

def _window_rows(db: Session, user_id: str, subject: str, limit: int = 7) -> list[LearningRecord]:
    rows = db.execute(
        select(LearningRecord).where(
            LearningRecord.user_id == user_id,
            LearningRecord.subject == subject,
        ).order_by(
            LearningRecord.started_at.desc(),
            LearningRecord.created_at.desc(),
            LearningRecord.id.desc(),
        ).limit(limit)
    ).scalars().all()
    return list(reversed(rows))


def _finalize_recommendation(
    db: Session, rec: Recommendation,
    items: list[dict], source: str, state_label: str,
    assessment_id: str | None, record_id: str | None, explain: str,
) -> None:
    rec.generation_status = "ready"
    rec.generation_source = source
    rec.generation_completed_at = datetime.utcnow()
    rec.items = json.dumps(items, ensure_ascii=False)
    rec.based_on_state_label = state_label
    rec.based_on_assessment_id = assessment_id
    rec.based_on_record_id = record_id
    rec.based_on_explain = explain
    db.commit()
    logger.info("[AI] 建议 %s 生成完成 source=%s items=%d", rec.id, source, len(items))


def _finalize_summary(
    db: Session, summ: Summary,
    content: dict, source: str,
    record_count: int, subjects: list[str],
    plan_completion_ratio: float | None, referenced_ids: list[str],
) -> None:
    summ.generation_status = "ready"
    summ.generation_source = source
    summ.generation_completed_at = datetime.utcnow()
    summ.content_overview = content.get("overview")
    summ.content_patterns = json.dumps(content.get("patterns", []), ensure_ascii=False)
    summ.content_suggestions = json.dumps(content.get("suggestions", []), ensure_ascii=False)
    summ.content_encouragement = content.get("encouragement")
    summ.data_record_count = record_count
    summ.data_subjects = json.dumps(subjects, ensure_ascii=False)
    summ.data_plan_completion_ratio = plan_completion_ratio
    summ.data_referenced_assessment_ids = json.dumps(referenced_ids, ensure_ascii=False)
    db.commit()
    logger.info("[AI] 复盘 %s 生成完成 source=%s", summ.id, source)


def _compute_plan_completion(db: Session, user_id: str) -> float | None:
    """简化版计划完成率（后续接 PlanTask 表后精确计算）。"""
    # TODO: 接 PlanTask 表算真实完成率
    return None


def _build_recommendation_prompt(
    subject: str, state_label: str,
    focus: int | None, fatigue: int | None,
    plan_ratio: float | None,
) -> str:
    return (
        f"你是一个学习状态助手。根据以下信息给出 1-2 条具体、可执行的学习建议。\n"
        f"学科：{subject}\n状态标签：{state_label}\n"
        f"专注度自评：{focus}/5\n疲劳度自评：{fatigue}/5\n"
        f"计划完成率：{plan_ratio}\n"
        f"要求：语气鼓励、中性、非评判；不涉及心理诊断或医疗建议；"
        f"每条建议包含 title（≤15字）和 content（≤100字）。"
    )


def _build_summary_prompt(rows, snap_rows, plan_ratio) -> str:
    return (
        f"你是一个学习状态助手。根据以下周期数据生成一份学习复盘。\n"
        f"记录数：{len(rows)}\n学科：{sorted(set(r.subject for r in rows))}\n"
        f"状态快照数：{len(snap_rows)}\n计划完成率：{plan_ratio}\n"
        f"要求：包含 overview（概述）、patterns（观察到的规律，列表）、"
        f"suggestions（建议，1-3条）、encouragement（鼓励收尾）；"
        f"必须基于真实数据，禁止编造；语气鼓励、中性；不涉及心理诊断。"
    )


def _parse_llm_items(text: str) -> list[dict] | None:
    """尝试从 LLM 文本解析出 items 列表。MVP 简化：期望 JSON。"""
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            return data
        if isinstance(data, dict) and "items" in data:
            return data["items"]
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _parse_llm_summary(text: str) -> dict | None:
    """尝试从 LLM 文本解析出 SummaryContent 结构。MVP 简化：期望 JSON。"""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "overview" in data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None

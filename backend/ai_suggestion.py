"""AI 建议生成编排层（PRD 5.3 / 5.4 / 6.4）。

职责：组装上下文 → 调 LLM provider → 安全审核 → 失败走兜底 → 写回 ORM。
不含公式计算（在 state_engine），不含 HTTP 逻辑（在 routes）。

生成模式（PRD 6.4 异步语义）：
- 路由用 FastAPI BackgroundTasks 调 run_recommendation_generation /
  run_summary_generation（本模块提供），POST 立即返回 pending 句柄；
- 后台任务自开 SessionLocal（路由请求的 session 在响应后已被 get_db
  关闭，不能复用），生成完把 ORM 行更新为终态；
- 前端轮询 GET /{id} 读终态。生成中 items 为 null（契约 0.3）。
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
    system, user = _build_recommendation_prompt(
        subject=subj,
        state_label=state_label,
        window_score=window.window_score if window.data_sufficient else None,
        trend=window.trend.value if window.trend else None,
        record_count=window.record_count,
        plan_completion_ratio=plan_completion_ratio,
        focus=trigger_record_row.self_report_focus if trigger_record_row else None,
        fatigue=trigger_record_row.self_report_fatigue if trigger_record_row else None,
        emotion=trigger_record_row.self_report_emotion if trigger_record_row else None,
        difficulty_feel=trigger_record_row.self_report_difficulty_feel if trigger_record_row else None,
        completion=trigger_record_row.behavior_completion if trigger_record_row else None,
        duration_minutes=trigger_record_row.duration_minutes if trigger_record_row else None,
        signals=window.signals,
        recent_rows_summary=_format_recent_records(
            list(rows) + ([trigger_record_row] if trigger_record_row and trigger_record_row not in rows else [])
        ),
    )
    llm_text = provider.generate(user, context={"system": system, "scene": scene, "subject": subj})

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


def _load_prompt_file(filename: str) -> str:
    """读 prompts/ 下的提示词模板。模板集中放文件，方便迭代与审计。"""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "prompts", filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_template_controls(text: str) -> tuple[str, str]:
    """把模板切成 (system, user) 两块。

    模板必须有两个独立行（位置任意）标记 SYSTEM / USER：
        SYSTEM:
        ...system body...
        USER:
        ...user body...
    用行级别定位，避免正则在长 body 里被 `#` 字符干扰。
    """
    import re
    sys_match = re.search(r"(?m)^#?\s*SYSTEM\s*:\s*$", text)
    user_match = re.search(r"(?m)^#?\s*USER\s*:\s*$", text)
    if not sys_match or not user_match or user_match.start() <= sys_match.end():
        raise ValueError("prompt template missing or malformed SYSTEM/USER markers")
    system = text[sys_match.end():user_match.start()].strip()
    user = text[user_match.end():].strip()
    return system, user


def _format_recent_records(rows: list) -> str:
    """最近 N 条记录的最简摘要（用于 prompt 上下文回顾）。"""
    lines = []
    for r in rows[-7:]:
        lines.append(
            f"- {r.started_at.strftime('%m-%d %H:%M')} "
            f"focus={r.self_report_focus} fatigue={r.self_report_fatigue} "
            f"emotion={r.self_report_emotion} completion={r.behavior_completion}"
        )
    return "\n".join(lines) or "（无历史记录）"


def _build_recommendation_prompt(
    subject: str, state_label: str,
    window_score: float | None,
    trend: str | None,
    record_count: int,
    plan_completion_ratio: float | None,
    focus: int | None, fatigue: int | None,
    emotion: str | None, difficulty_feel: str | None,
    completion: str | None, duration_minutes: int | None,
    signals: list[str],
    recent_rows_summary: str,
) -> tuple[str, str]:
    """从 prompts/suggestion.txt 渲染 system/user 两段。

    返回 (system, user)，调用方分别作为 chat 的 system / user message 发送。
    这样能保留 system role 的硬约束，符合 OpenAI/Anthropic 通用约定。
    """
    template = _load_prompt_file("suggestion.txt")
    system, user = _strip_template_controls(template)

    user = user.format(
        subject=subject,
        stateLabel=state_label,
        windowScore=window_score if window_score is not None else "null（数据不足）",
        trend=trend if trend is not None else "null（数据不足）",
        recordCount=record_count,
        planCompletionRatio=(
            f"{plan_completion_ratio:.2f}" if plan_completion_ratio is not None
            else "null（未接入计划）"
        ),
        focus=focus if focus is not None else "null",
        fatigue=fatigue if fatigue is not None else "null",
        emotion=emotion if emotion is not None else "null",
        difficultyFeel=difficulty_feel if difficulty_feel is not None else "null",
        completion=completion if completion is not None else "null",
        durationMinutes=duration_minutes if duration_minutes is not None else "null",
        signals=("; ".join(signals) if signals else "（无特殊信号）"),
        recentRecordsSummary=recent_rows_summary,
    )
    return system, user


def _build_summary_prompt(rows, snap_rows, plan_ratio) -> str:
    return (
        f"你是一个学习状态助手。根据以下周期数据生成一份学习复盘。\n"
        f"记录数：{len(rows)}\n学科：{sorted(set(r.subject for r in rows))}\n"
        f"状态快照数：{len(snap_rows)}\n计划完成率：{plan_ratio}\n"
        f"要求：包含 overview（概述）、patterns（观察到的规律，列表）、"
        f"suggestions（建议，1-3条）、encouragement（鼓励收尾）；"
        f"必须基于真实数据，禁止编造；语气鼓励、中性；不涉及心理诊断。"
    )


def _extract_json_block(text: str) -> str:
    """LLM 输出容错第 1 层：提取 markdown ```json ... ``` 围栏里的内容。

    即使 prompt 明确要求纯 JSON，模型偶发仍会包一层 ``` 或加前后说明文字。
    提不出来就原样返回，让第 2 层（json.loads）自行判断。
    """
    import re

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text


def _parse_llm_items(text: str) -> list[dict] | None:
    """从 LLM 文本解析 items 列表，两层容错：先纯 JSON、再 markdown 围栏提取。"""
    for candidate in (text, _extract_json_block(text)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list) and data:
            return data
        if isinstance(data, dict) and isinstance(data.get("items"), list) and data["items"]:
            return data["items"]
    return None


def _parse_llm_summary(text: str) -> dict | None:
    """从 LLM 文本解析 SummaryContent 结构，两层容错同 _parse_llm_items。"""
    for candidate in (text, _extract_json_block(text)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "overview" in data:
            return data
    return None


# ---------- 后台任务入口（供 BackgroundTasks 调用；自开 session，不复用请求级 session） ----------

def run_recommendation_generation(
    recommendation_id: str,
    user_id: str,
    scene: str,
    subject: str | None,
    record_id: str | None,
) -> None:
    """后台生成建议。路由响应返回后执行，耗时的 LLM 调用不阻塞用户。"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        trigger = db.get(LearningRecord, record_id) if record_id else None
        generate_recommendation(db, recommendation_id, user_id, scene, subject, record_id, trigger)
    except Exception:
        # 后台任务没有调用方可接异常；失败时行停在 pending，
        # 由生成函数内部的兜底/failed 逻辑保证状态推进，这里只记日志。
        logger.exception("[AI] 后台建议生成异常 recommendation_id=%s", recommendation_id)
    finally:
        db.close()


def run_summary_generation(
    summary_id: str,
    user_id: str,
    period_start,
    period_end,
) -> None:
    """后台生成复盘。同 run_recommendation_generation。"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        generate_summary(db, summary_id, user_id, period_start, period_end)
    except Exception:
        logger.exception("[AI] 后台复盘生成异常 summary_id=%s", summary_id)
    finally:
        db.close()

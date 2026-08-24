"""学科级自动周复盘定时任务（板块二 v2.2-4，计划书与团队 backlog 共同盲区补录）。

触发条件（PRD 12.3.5）：用户在「该学科本周（最近 7 天）」累计 ≥3 条学习记录或错题记录，
系统每日扫描一次，对满足条件的 (user, subject) 触发知识复盘生成；已为该周生成过的跳过。

实现：FastAPI startup 挂 asyncio 定时器，每日 03:00 本地时间跑一次（MVP 单机，不引 APScheduler）。
系统触发的复盘不计入用户每日手动限额（rate_limit_summary_per_day）——这是系统批量，不走
knowledge-summary 路由的进程内 dict。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# 触发阈值：本周该学科记录数下限
MIN_WEEKLY_RECORDS = 3
SCAN_HOUR = 3  # 本地时间凌晨 3 点扫描

__all__ = ["start_weekly_summary_scheduler", "run_weekly_scan"]


def _eligible_users_subjects(db) -> list[tuple[str, str]]:
    """返回本周满足触发条件的 (user_id, subject_code) 列表。

    学习记录（learning_records）+ 错题记录（kb_errors）合计 ≥ MIN_WEEKLY_RECORDS。
    用 UNION 聚合，避免两表分别不达标但合计达标的漏判。
    """
    from sqlalchemy import func, select, literal, union_all

    from models.knowledge import ErrorRecord as ErrorRecordORM
    from models.learning_record import LearningRecord as LearningRecordORM

    since = datetime.utcnow() - timedelta(days=7)

    lr = (
        select(
            LearningRecordORM.user_id.label("uid"),
            LearningRecordORM.subject.label("subj"),
        )
        .where(LearningRecordORM.created_at >= since)
    )
    er = (
        select(
            ErrorRecordORM.user_id.label("uid"),
            ErrorRecordORM.subject.label("subj"),
        )
        .where(
            ErrorRecordORM.created_at >= since,
            ErrorRecordORM.deleted_at.is_(None),
        )
    )
    combined = union_all(lr, er).subquery()
    rows = db.execute(
        select(
            combined.c.uid,
            combined.c.subj,
            func.count().label("cnt"),
        )
        .group_by(combined.c.uid, combined.c.subj)
        .having(func.count() >= MIN_WEEKLY_RECORDS)
    ).all()
    return [(r[0], r[1]) for r in rows]


def _already_generated_this_week(db, user_id: str, subject: str) -> bool:
    """该用户该学科本周是否已生成过 knowledge 维度复盘。"""
    from sqlalchemy import func, select

    from models.summary import Summary as SummaryORM

    week_start = date.today() - timedelta(days=date.today().weekday())  # 周一
    exists = db.execute(
        select(func.count())
        .select_from(SummaryORM)
        .where(
            SummaryORM.user_id == user_id,
            SummaryORM.dimension == "knowledge",
            SummaryORM.period_start >= week_start,
        )
    ).scalar_one()
    return exists > 0


def _generate_for(db, user_id: str, subject: str) -> str | None:
    """对单 (user, subject) 生成知识复盘（复用 routes/knowledge 的 prompt 与 persist 逻辑，
    但绕过路由层限流 dict）。返回 summary 文本或 None。
    """
    from llm_provider import get_provider
    from routes.knowledge import (
        KNOWLEDGE_SUMMARY_FALLBACK,
        KNOWLEDGE_SUMMARY_SYSTEM,
    )
    from schemas.knowledge import KnowledgeSummaryCreate

    payload = KnowledgeSummaryCreate(subject=subject, period="weekly_auto")
    user_prompt = (
        f"学科：{payload.subject}\n"
        f"周期：{payload.period}\n"
        "请基于结构化特征生成本周知识复盘（系统自动触发，无错题原文，仅做常规学业建议）。"
    )
    text: str | None = None
    try:
        provider = get_provider()
        text = provider.generate(
            user_prompt,
            context={
                "system": KNOWLEDGE_SUMMARY_SYSTEM,
                "scene": "knowledge_summary_auto",
                "subject": subject,
                "egress_fields": {"subject": subject, "period": payload.period},
                "data_class": "knowledge_aggregated",
            },
        )
        if text:
            from safety_filter import check
            passed, reason = check(text)
            if not passed:
                logger.info("[WEEKLY_KS] 审核拦截 user=%s subj=%s: %s", user_id, subject, reason)
                text = None
    except Exception as e:  # noqa: BLE001
        logger.warning("[WEEKLY_KS] LLM 异常 user=%s subj=%s: %s", user_id, subject, e)
        return None

    summary_text = text.strip() if text and text.strip() else KNOWLEDGE_SUMMARY_FALLBACK
    # 复用路由层 persist（自开 session，失败仅记日志）
    from routes.knowledge import _persist_knowledge_summary
    _persist_knowledge_summary(user_id, payload, summary_text, source="llm" if text else "template")
    return summary_text


def run_weekly_scan() -> dict:
    """同步执行一次扫描（供定时器与测试调用）。返回 {scanned, generated, skipped, failed}。"""
    from database import SessionLocal

    stats = {"scanned": 0, "generated": 0, "skipped": 0, "failed": 0}
    db = SessionLocal()
    try:
        targets = _eligible_users_subjects(db)
        stats["scanned"] = len(targets)
        for user_id, subject in targets:
            try:
                if _already_generated_this_week(db, user_id, subject):
                    stats["skipped"] += 1
                    continue
                _generate_for(db, user_id, subject)
                stats["generated"] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed"] += 1
                logger.warning("[WEEKLY_KS] 生成失败 user=%s subj=%s: %s", user_id, subject, e)
    finally:
        db.close()
    logger.info("[WEEKLY_KS] 扫描完成: %s", stats)
    return stats


async def _scheduler_loop() -> None:
    """每日 SCAN_HOUR 触发一次；启动后立即跑一次（便于联调），之后每日一次。"""
    while True:
        try:
            run_weekly_scan()
        except Exception as e:  # noqa: BLE001 — 定时器绝不能因单次失败退出
            logger.warning("[WEEKLY_KS] 定时扫描异常: %s", e)
        # 简化：每 24h 跑一次（MVP 不追求精确到点）
        await asyncio.sleep(24 * 3600)


def start_weekly_summary_scheduler() -> asyncio.Task | None:
    """FastAPI startup 调用；失败仅记日志，不阻断启动。"""
    try:
        return asyncio.create_task(_scheduler_loop())
    except Exception as e:  # noqa: BLE001
        logger.warning("[WEEKLY_KS] 启动定时器失败: %s", e)
        return None

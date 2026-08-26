"""自动周复盘定时任务测试（W3-1）。

覆盖触发条件：
- 本周学习记录 + 错题记录合计 ≥3 → 触发
- 不足 3 → 不触发
- 已生成过本周 knowledge 复盘 → 跳过
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database import SessionLocal
from models.goal import Goal as GoalORM
from models.knowledge import ErrorRecord as ErrorRecordORM, KnowledgeSubject as KnowledgeSubjectORM
from models.learning_record import LearningRecord as LearningRecordORM
from models.summary import Summary as SummaryORM


def _mk_record(db, user_id, subject, n, use_error=True):
    for i in range(n):
        if use_error:
            db.add(ErrorRecordORM(
                id=f"err_{user_id}_{i}", user_id=user_id, subject=subject,
                raw_text="x", status="open",
            ))
        else:
            db.add(LearningRecordORM(
                id=f"lr_{user_id}_{i}", user_id=user_id, subject=subject,
                started_at=datetime.utcnow() - timedelta(days=1),
                duration_minutes=30,
                behavior_completion="completed",
                behavior_interruptions=0,
                self_report_focus=3,
                self_report_fatigue=3,
                self_report_emotion="neutral",
                self_report_difficulty_feel="moderate",
            ))


@pytest.fixture(autouse=True)
def _seed():
    db = SessionLocal()
    try:
        db.add(KnowledgeSubjectORM(id="ks_math", code="SX", name="数学", version="1.0", enabled=True))
        db.commit()
    finally:
        db.close()
    yield


def test_eligible_requires_three_records():
    from jobs.weekly_knowledge_summary import _eligible_users_subjects

    db = SessionLocal()
    try:
        # u_ok：2 学习记录 + 1 错题 = 3
        _mk_record(db, "u_ok", "SX", 2, use_error=False)
        _mk_record(db, "u_ok", "SX", 1, use_error=True)
        # u_few：仅 2 条
        _mk_record(db, "u_few", "SX", 2, use_error=False)
        db.commit()

        targets = _eligible_users_subjects(db)
        pairs = set(targets)
        assert ("u_ok", "SX") in pairs
        assert ("u_few", "SX") not in pairs
    finally:
        db.close()


def test_run_scan_skips_already_generated():
    from jobs.weekly_knowledge_summary import run_weekly_scan

    db = SessionLocal()
    try:
        _mk_record(db, "u_gen", "SX", 3, use_error=True)
        # 预置一条本周 knowledge 复盘 → 应被跳过
        db.add(SummaryORM(
            id="sum_prev", user_id="u_gen", dimension="knowledge",
            period_start=datetime.utcnow().date(), period_end=datetime.utcnow().date(),
            generation_status="ready", content_overview="上周内容",
        ))
        db.commit()

        stats = run_weekly_scan()
        # u_gen 已生成过 → skipped；无其他达标用户 → generated 0
        assert stats["scanned"] >= 1
        assert stats["generated"] == 0
        assert stats["skipped"] >= 1
    finally:
        db.close()


def test_run_scan_generates_when_eligible_and_not_yet():
    from jobs.weekly_knowledge_summary import run_weekly_scan
    from sqlalchemy import select

    db = SessionLocal()
    try:
        _mk_record(db, "u_new", "SX", 3, use_error=True)
        db.commit()

        stats = run_weekly_scan()
        assert stats["generated"] >= 1

        # 落库了 dimension=knowledge 的复盘（MockProvider → template 兜底仍落库）
        rows = db.execute(
            select(SummaryORM).where(
                SummaryORM.user_id == "u_new", SummaryORM.dimension == "knowledge"
            )
        ).scalars().all()
        assert len(rows) >= 1
    finally:
        db.close()

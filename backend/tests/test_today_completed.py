"""今日计划完成计数相关工具函数测试（PRD 5.3 建议 + 5.4 复盘）。

覆盖：
- _compute_today_completed_tasks：今日已完成的 plan_tasks 列表
- _compute_today_task_total：completed / total
- 边界：无 plan / 全 0 / 含软删除 / 跨日
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from ai_suggestion import _compute_today_completed_tasks, _compute_today_task_total
from database import SessionLocal
from models.plan import Plan, PlanTask
from models.user import User


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _seed_user_and_plan(user_id: str, plan_date, task_specs: list[dict]) -> str:
    """seed 一个 user + plan + tasks，返回 plan_id。

    plan_date 可以是 str (YYYY-MM-DD) 或 datetime.date 对象。
    task_specs: [{"subject", "topic", "estimated_minutes", "status"}, ...]
    status 默认 'pending'。
    """
    if isinstance(plan_date, str):
        plan_date = date.fromisoformat(plan_date)
    db = SessionLocal()
    try:
        # 确保 user 行存在（profiles 走 User 路由创建，这里直接 upsert）
        u = db.get(User, user_id)
        if u is None:
            db.add(User(id=user_id, stage="senior", grade="高二",
                        subjects=["SX"], onboarding_completed=True))
            db.commit()
        plan_id = f"p_{user_id}_{_uid()}"
        db.add(Plan(id=plan_id, user_id=user_id, plan_date=plan_date, available_minutes=60))
        db.commit()
        for i, spec in enumerate(task_specs):
            db.add(PlanTask(
                id=f"t_{plan_id}_{i}",
                plan_id=plan_id,
                user_id=user_id,
                subject=spec.get("subject", "SX"),
                topic=spec.get("topic", f"任务 {i}"),
                estimated_minutes=spec.get("estimated_minutes", 30),
                priority=i + 1,
                status=spec.get("status", "pending"),
                removed=spec.get("removed", False),
            ))
        db.commit()
        return plan_id
    finally:
        db.close()


def test_today_completed_empty_when_no_plan():
    user = f"u_no_plan_{_uid()}"
    rows = _compute_today_completed_tasks(SessionLocal(), user)
    assert rows == []


def test_today_completed_returns_only_completed():
    user = f"u_{_uid()}"
    plan_id = _seed_user_and_plan(user, date.today().isoformat(), [
        {"topic": "已完成A", "status": "completed"},
        {"topic": "已完成B", "status": "completed"},
        {"topic": "未完成C", "status": "pending"},
    ])
    db = SessionLocal()
    try:
        rows = _compute_today_completed_tasks(db, user)
        assert len(rows) == 2
        topics = {r["topic"] for r in rows}
        assert topics == {"已完成A", "已完成B"}
        # 字段完整性
        for r in rows:
            assert "taskId" in r
            assert r["subject"] == "SX"
            assert r["estimatedMinutes"] == 30
            assert r["priority"] >= 1
    finally:
        db.close()


def test_today_completed_excludes_removed():
    user = f"u_{_uid()}"
    _seed_user_and_plan(user, date.today().isoformat(), [
        {"topic": "可见", "status": "completed"},
        {"topic": "软删除", "status": "completed", "removed": True},
    ])
    db = SessionLocal()
    try:
        rows = _compute_today_completed_tasks(db, user)
        assert len(rows) == 1
        assert rows[0]["topic"] == "可见"
    finally:
        db.close()


def test_today_completed_sorted_by_priority():
    user = f"u_{_uid()}"
    # 列表顺序在 _seed_user_and_plan 里被映射成 priority=1,2,3
    _seed_user_and_plan(user, date.today().isoformat(), [
        {"topic": "first",  "status": "completed"},  # priority=1
        {"topic": "second", "status": "completed"},  # priority=2
        {"topic": "third",  "status": "completed"},  # priority=3
    ])
    db = SessionLocal()
    try:
        rows = _compute_today_completed_tasks(db, user)
        # 按 priority 升序：first → second → third
        assert [r["topic"] for r in rows] == ["first", "second", "third"]
    finally:
        db.close()


def test_today_completed_excludes_other_days():
    user = f"u_{_uid()}"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _seed_user_and_plan(user, yesterday, [
        {"topic": "昨天的", "status": "completed"},
    ])
    db = SessionLocal()
    try:
        rows = _compute_today_completed_tasks(db, user)
        assert rows == [], "昨日的计划任务不应算作今日完成"
    finally:
        db.close()


def test_today_task_total_counts():
    user = f"u_{_uid()}"
    _seed_user_and_plan(user, date.today().isoformat(), [
        {"status": "completed"},
        {"status": "completed"},
        {"status": "pending"},
        {"status": "pending"},
        {"status": "pending"},
    ])
    db = SessionLocal()
    try:
        completed, total = _compute_today_task_total(db, user)
        assert (completed, total) == (2, 5)
    finally:
        db.close()


def test_today_task_total_no_plan():
    user = f"u_no_plan2_{_uid()}"
    db = SessionLocal()
    try:
        completed, total = _compute_today_task_total(db, user)
        assert (completed, total) == (0, 0)
    finally:
        db.close()
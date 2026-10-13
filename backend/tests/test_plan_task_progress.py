"""提交学习记录时推进计划任务状态（PRD 5.3 修正）。

背景
----
`_sync_plan_task` 曾经把**单次自评的 completion** 直接写进 `plan_tasks.status`：

    task.status = completion          # completion ∈ {completed, partial, abandoned}

这与 PRD 5.3 冲突——任务状态应由**累计专注时长是否跑满 estimated_minutes** 决定；
单次自评「放弃」只落到 learning_record 的行为数据（behavior_completion），
不得把整个任务划成「已放弃」。任务放弃只能由用户在任务列表显式操作。

本文件守住的语义（与 record_service._sync_plan_task 的 docstring 一一对应）：
1. 跑满 estimated_minutes → completed
2. 没跑满 → partial（哪怕这次自评写的是 completed）
3. 单次自评 abandoned **不**把任务划成 abandoned
4. 用户已显式 PATCH 成 abandoned 的任务，自动同步**不**把它翻回 completed/partial
5. 别人的任务不受影响（user_id 归属校验）
6. user_adjusted 不被自动同步改动
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from database import SessionLocal
from models.learning_record import LearningRecord
from models.plan import Plan, PlanTask
from models.user import User
from record_service import _sync_plan_task
from schemas.learning_record import RecordBehavior, RecordInput


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _seed(user_id: str, *, estimated_minutes: int = 30, task_status: str = "pending",
          user_adjusted: bool = False) -> tuple[str, str]:
    """建 user + plan + 一个 task，返回 (user_id, task_id)。"""
    db = SessionLocal()
    try:
        if db.get(User, user_id) is None:
            db.add(User(id=user_id, stage="senior", grade="初三",
                        subjects=["SX"], onboarding_completed=True))
            db.commit()
        plan_id = f"p_{user_id}_{_uid()}"
        task_id = f"t_{plan_id}_0"
        db.add(Plan(id=plan_id, user_id=user_id, plan_date=date.today(), available_minutes=60))
        db.commit()
        db.add(PlanTask(
            id=task_id, plan_id=plan_id, user_id=user_id, subject="SX", topic="函数单调性",
            estimated_minutes=estimated_minutes, priority=1, status=task_status,
            removed=False, user_adjusted=user_adjusted,
        ))
        db.commit()
        return user_id, task_id
    finally:
        db.close()


def _add_record(user_id: str, task_id: str, minutes: int, completion: str = "partial") -> None:
    """直接落一条学习记录（不经 persist_record，只为构造累计时长）。"""
    db = SessionLocal()
    try:
        db.add(LearningRecord(
            id=f"r_{uuid.uuid4().hex[:12]}", user_id=user_id, subject="SX",
            started_at=datetime.utcnow() - timedelta(minutes=minutes), duration_minutes=minutes,
            plan_task_id=task_id, behavior_completion=completion,
            behavior_interruptions=0, source="self_report", skip_recommendation=True,
        ))
        db.commit()
    finally:
        db.close()


def _status(task_id: str) -> str:
    db = SessionLocal()
    try:
        return db.get(PlanTask, task_id).status
    finally:
        db.close()


# --------------------------------------------------------------------------
# 1 / 2：状态按累计时长推进，不按单次自评
# --------------------------------------------------------------------------

def test_accumulated_reaching_estimate_marks_completed():
    """跑满 estimated_minutes → completed。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=30)
    _add_record(user_id, task_id, minutes=10)
    _add_record(user_id, task_id, minutes=10)
    _add_record(user_id, task_id, minutes=10)   # 累计 30 = 30
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "completed"


def test_accumulated_below_estimate_marks_partial_even_when_self_report_completed():
    """没跑满 → partial，**哪怕这次自评写的是 completed**。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=30)
    _add_record(user_id, task_id, minutes=10, completion="completed")   # 累计 10 < 30
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "partial"


def test_single_sufficient_record_marks_completed():
    """单条记录就跑满 → completed。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=25)
    _add_record(user_id, task_id, minutes=25)
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "completed"


# --------------------------------------------------------------------------
# 3：单次自评「放弃」不把任务划成 abandoned —— PRD 5.3 修正，必须有断言守住
# --------------------------------------------------------------------------

def test_single_self_report_abandoned_does_not_mark_task_abandoned():
    """单次自评「放弃」只落 behavior_completion，任务状态仍是 partial。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=30)
    _add_record(user_id, task_id, minutes=10, completion="abandoned")
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "partial", "单次自评「放弃」不得把任务划成 abandoned"


def test_self_report_abandoned_still_completes_when_time_is_sufficient():
    """自评写 abandoned 但累计跑满 → completed（状态只看时长）。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=20)
    _add_record(user_id, task_id, minutes=20, completion="abandoned")
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "completed"


# --------------------------------------------------------------------------
# 4：用户已显式放弃的任务，自动同步不得复活
# --------------------------------------------------------------------------

def test_explicitly_abandoned_task_is_not_revived():
    """用户 PATCH status=abandoned 后再提交记录，任务不能自己活过来。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=15, task_status="abandoned")
    _add_record(user_id, task_id, minutes=60)   # 远超 estimated，自动同步会判 completed
    _sync_plan_task(SessionLocal(), user_id, task_id)
    assert _status(task_id) == "abandoned", "用户显式放弃的任务不得被自动同步翻回"


# --------------------------------------------------------------------------
# 5 / 6：归属校验与 user_adjusted 不被改
# --------------------------------------------------------------------------

def test_other_users_task_is_untouched():
    """传入别人的 user_id → 不动别人的任务。"""
    owner_id, task_id = _seed(_uid(), estimated_minutes=30)
    _add_record(owner_id, task_id, minutes=30)
    _sync_plan_task(SessionLocal(), f"someone_else_{_uid()}", task_id)
    assert _status(task_id) == "pending", "归属校验失败时不得改状态"


def test_user_adjusted_flag_preserved():
    """自动同步只改 status，不动 user_adjusted。"""
    user_id, task_id = _seed(_uid(), estimated_minutes=10, user_adjusted=True)
    _add_record(user_id, task_id, minutes=10)
    _sync_plan_task(SessionLocal(), user_id, task_id)
    db = SessionLocal()
    try:
        task = db.get(PlanTask, task_id)
        assert task.user_adjusted is True
        assert task.status == "completed"
    finally:
        db.close()


def test_missing_task_is_noop():
    """任务不存在 → 不抛异常。"""
    _sync_plan_task(SessionLocal(), _uid(), f"t_not_exists_{_uid()}")


# --------------------------------------------------------------------------
# 7：端到端 —— 经 persist_record 提交，验证累计时长口径真的接上了
# --------------------------------------------------------------------------

def test_persist_record_advances_task_status_by_accumulated_minutes():
    """走 persist_record 全链路：单次自评 completed 但时长不够 → 任务应为 partial。"""
    from record_service import persist_record

    user_id, task_id = _seed(_uid(), estimated_minutes=45)
    body = RecordInput(
        subject="SX",
        started_at=datetime.utcnow() - timedelta(minutes=15),
        duration_minutes=15,
        plan_task_id=task_id,
        behavior=RecordBehavior(completion="completed", accuracy=0.8, interruptions=0),
        skip_recommendation=True,
    )
    db = SessionLocal()
    try:
        persist_record(db, user_id, body, background_tasks=None)
    finally:
        db.close()
    assert _status(task_id) == "partial"

    # 再补一条把累计推到 60 ≥ 45
    body2 = RecordInput(
        subject="SX",
        started_at=datetime.utcnow() - timedelta(minutes=30),
        duration_minutes=30,
        plan_task_id=task_id,
        behavior=RecordBehavior(completion="partial", accuracy=0.8, interruptions=0),
        skip_recommendation=True,
    )
    db = SessionLocal()
    try:
        persist_record(db, user_id, body2, background_tasks=None)
    finally:
        db.close()
    assert _status(task_id) == "completed", "累计 45 ≥ estimated 45 应推进到 completed"


def test_persist_record_single_abandoned_does_not_abandon_task():
    """端到端：单次自评 abandoned → 任务不是 abandoned（PRD 5.3 回归护栏）。"""
    from record_service import persist_record

    user_id, task_id = _seed(_uid(), estimated_minutes=60)
    body = RecordInput(
        subject="SX",
        started_at=datetime.utcnow() - timedelta(minutes=10),
        duration_minutes=10,
        plan_task_id=task_id,
        behavior=RecordBehavior(completion="abandoned", accuracy=0.5, interruptions=0),
        skip_recommendation=True,
    )
    db = SessionLocal()
    try:
        persist_record(db, user_id, body, background_tasks=None)
    finally:
        db.close()
    assert _status(task_id) == "partial"
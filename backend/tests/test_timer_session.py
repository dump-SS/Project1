"""计时会话测试（D30 双模式恢复 / D31 僵尸治理 / D32 到点软提醒 / #14 分段）。

覆盖的是**服务端口径**，不是前端表现：
- 刷新/断线后按 mode 正确恢复（这是"路由 state 丢上下文"技术债的根治点）；
- 有效时长 ≠ 墙上时长（倒计时封顶 target）；
- 僵尸会话**不产生学习记录**（宁可少记，也不凭空造时长）；
- 不允许并行计时（一会话内只能分段）。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from database import SessionLocal
from main import app
from models.plan import Plan, PlanTask
from models.timer import TimerSegment, TimerSession

client = TestClient(app)

HDR = {"X-User-ID": "u_test_timer"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _shift(session_id: str, *, started_minutes_ago: float | None = None,
           heartbeat_minutes_ago: float = 0) -> None:
    """把会话的 started_at / last_heartbeat_at 挪到过去，用于构造"跑了很久"的场景。

    ⚠️ 心跳必须单独控制：只挪 started_at 会让会话同时命中"断连"判定，
    测不出「到点封顶」这类不涉及断连的分支。
    """
    db = SessionLocal()
    try:
        row = db.get(TimerSession, session_id)
        if started_minutes_ago is not None:
            row.started_at = _now() - timedelta(minutes=started_minutes_ago)
            for seg in db.execute(
                select(TimerSegment).where(TimerSegment.session_id == session_id)
            ).scalars():
                if seg.ended_at is None:
                    seg.started_at = row.started_at
        row.last_heartbeat_at = _now() - timedelta(minutes=heartbeat_minutes_ago)
        db.commit()
    finally:
        db.close()


def _start(**over):
    body = {"mode": "countdown", "targetMinutes": 30}
    body.update(over)
    return client.post("/api/v1/timer-sessions", json=body, headers=HDR)


def _seed_plan_task(user_id: str, subject: str = "WL") -> str:
    db = SessionLocal()
    try:
        plan_id = f"p_{uuid.uuid4().hex[:8]}"
        task_id = f"t_{uuid.uuid4().hex[:8]}"
        db.add(Plan(id=plan_id, user_id=user_id, plan_date=date.today(), available_minutes=60))
        db.commit()
        db.add(PlanTask(id=task_id, plan_id=plan_id, user_id=user_id, subject=subject,
                        topic="力学 · 综合", estimated_minutes=30, priority=1, status="pending"))
        db.commit()
        return task_id
    finally:
        db.close()


# ---------- 开始与恢复 ----------


def test_start_countdown_and_current():
    sid = _start().json()["sessionId"]
    r = client.get("/api/v1/timer-sessions/current", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["session"]["status"] == "running"
    assert body["restore"]["mode"] == "countdown"
    # 刚开 1 秒内，剩余应接近 1800
    assert 1790 <= body["restore"]["remainingSeconds"] <= 1800
    assert body["restore"]["needsVerdict"] is False
    assert body["session"]["segments"][0]["segmentId"].startswith("seg_")
    assert sid == body["session"]["sessionId"]


def test_current_inactive_when_no_session():
    """没有会话是正常流程，不是错误——前端每次进计时页都会问一次。"""
    r = client.get("/api/v1/timer-sessions/current", headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"active": False, "session": None, "restore": None}


def test_countdown_requires_target_minutes():
    r = _start(targetMinutes=None)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "targetMinutes"


def test_countup_ignores_target_minutes():
    r = client.post("/api/v1/timer-sessions",
                    json={"mode": "countup", "targetMinutes": 25}, headers=HDR)
    assert r.status_code == 201
    assert r.json()["targetMinutes"] is None

    cur = client.get("/api/v1/timer-sessions/current", headers=HDR).json()
    assert cur["restore"]["mode"] == "countup"
    assert cur["restore"]["remainingSeconds"] is None
    assert cur["restore"]["elapsedSeconds"] is not None


def test_second_start_conflicts():
    """不允许并行计时：已有会话时必须先处置，不静默接管也不静默丢弃。"""
    _start()
    r = _start()
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STATE_CONFLICT"


def test_subject_derived_from_task():
    task_id = _seed_plan_task("u_test_timer", subject="WL")
    sid = _start(taskId=task_id).json()["sessionId"]
    got = client.get(f"/api/v1/timer-sessions/{sid}", headers=HDR).json()
    assert got["subject"] == "WL"


def test_subject_falls_back_to_other():
    sid = _start().json()["sessionId"]
    assert client.get(f"/api/v1/timer-sessions/{sid}", headers=HDR).json()["subject"] == "other"


# ---------- 心跳与分段 ----------


def test_heartbeat_refreshes_last_seen():
    sid = _start().json()["sessionId"]
    _shift(sid, heartbeat_minutes_ago=10)
    before = client.get(f"/api/v1/timer-sessions/{sid}", headers=HDR).json()["lastHeartbeatAt"]

    r = client.post(f"/api/v1/timer-sessions/{sid}/heartbeat", headers=HDR)
    assert r.status_code == 200
    assert r.json()["lastHeartbeatAt"] > before


def test_switch_task_closes_previous_segment():
    task_id = _seed_plan_task("u_test_timer", subject="SX")
    sid = _start().json()["sessionId"]

    r = client.post(f"/api/v1/timer-sessions/{sid}/segments",
                    json={"taskId": task_id}, headers=HDR)
    assert r.status_code == 201
    assert r.json()["taskId"] == task_id

    session = client.get(f"/api/v1/timer-sessions/{sid}", headers=HDR).json()
    segs = session["segments"]
    assert len(segs) == 2
    # 上一段已被关闭并结算秒数，最后一段仍开着
    assert segs[0]["endedAt"] is not None and segs[0]["seconds"] is not None
    assert segs[1]["endedAt"] is None
    # 会话主任务跟着走（收尾时记录要挂到最后在做的那件事上）
    assert session["taskId"] == task_id
    assert session["subject"] == "SX"


# ---------- 收尾：有效时长口径 ----------


def _finish(sid, **over):
    body = {
        "completion": "completed",
        "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
    }
    body.update(over)
    return client.post(f"/api/v1/timer-sessions/{sid}/finish", json=body, headers=HDR)


def test_finish_writes_record_and_closes_session():
    sid = _start().json()["sessionId"]
    r = _finish(sid, durationMinutes=20)
    assert r.status_code == 201
    body = r.json()
    assert body["durationMinutes"] == 20
    assert body["behavior"]["completion"] == "completed"
    assert body["note"] is None

    # 会话已结束，不再是"当前会话"
    assert client.get("/api/v1/timer-sessions/current", headers=HDR).json()["active"] is False
    # 有效时长落库（秒）
    db = SessionLocal()
    try:
        assert db.get(TimerSession, sid).effective_seconds == 20 * 60
    finally:
        db.close()


def test_countdown_caps_effective_duration_at_target():
    """D31：倒计时有效时长 = min(经过, target)。跑了 45 分钟也只记 30 分钟。"""
    sid = _start(targetMinutes=30).json()["sessionId"]
    _shift(sid, started_minutes_ago=45, heartbeat_minutes_ago=0)

    r = _finish(sid)
    assert r.status_code == 201
    assert r.json()["durationMinutes"] == 30


def test_countup_records_actual_elapsed():
    sid = client.post("/api/v1/timer-sessions", json={"mode": "countup"}, headers=HDR).json()["sessionId"]
    _shift(sid, started_minutes_ago=50, heartbeat_minutes_ago=0)

    r = _finish(sid)
    assert r.status_code == 201
    assert r.json()["durationMinutes"] == 50


def test_finish_twice_conflicts():
    sid = _start().json()["sessionId"]
    assert _finish(sid, durationMinutes=5).status_code == 201
    again = _finish(sid, durationMinutes=5)
    assert again.status_code == 409


def test_finish_syncs_plan_task_status():
    """收尾落记录时，关联任务状态要跟着变（PRD 5.3 计划完成计数实时反映）。"""
    task_id = _seed_plan_task("u_test_timer", subject="SX")
    sid = _start(taskId=task_id).json()["sessionId"]
    _finish(sid, durationMinutes=25, completion="completed")

    db = SessionLocal()
    try:
        assert db.get(PlanTask, task_id).status == "completed"
    finally:
        db.close()


# ---------- 僵尸治理（D31） ----------


def test_stale_session_needs_verdict_and_blocks_auto_finish():
    """断连超过阈值 → 判异常：不得自动记账，收尾必须先给出时长。"""
    sid = _start().json()["sessionId"]
    _shift(sid, started_minutes_ago=90, heartbeat_minutes_ago=60)

    cur = client.get("/api/v1/timer-sessions/current", headers=HDR).json()
    assert cur["restore"]["needsVerdict"] is True
    # 裁决卡预填值 = 倒计时封顶 target
    assert cur["restore"]["suggestedMinutes"] == 30

    blocked = _finish(sid)
    assert blocked.status_code == 400
    assert blocked.json()["error"]["field"] == "durationMinutes"


def test_verdict_then_manual_duration():
    """裁决卡第三态「手动改时长」：显式传 durationMinutes 即以它为准。"""
    sid = _start(targetMinutes=30).json()["sessionId"]
    _shift(sid, started_minutes_ago=90, heartbeat_minutes_ago=60)

    r = _finish(sid, durationMinutes=42)
    assert r.status_code == 201
    assert r.json()["durationMinutes"] == 42


def test_discard_produces_no_record():
    """D31 验收：僵尸会话不产生记录。"""
    sid = _start().json()["sessionId"]
    _shift(sid, started_minutes_ago=90, heartbeat_minutes_ago=60)

    r = client.delete(f"/api/v1/timer-sessions/{sid}", headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"discarded": True, "sessionId": sid}

    assert client.get("/api/v1/learning-records", headers=HDR).json()["items"] == []
    db = SessionLocal()
    try:
        row = db.get(TimerSession, sid)
        assert row.status == "abandoned"
        # 不写 effective_seconds：没有可信时长就不留一个会被误读的数字
        assert row.effective_seconds is None
    finally:
        db.close()


def test_countup_over_limit_needs_verdict():
    """正计时没有"到点"兜底，是僵尸重灾区：超上限必须裁决。"""
    sid = client.post("/api/v1/timer-sessions", json={"mode": "countup"}, headers=HDR).json()["sessionId"]
    _shift(sid, started_minutes_ago=400, heartbeat_minutes_ago=1)  # 400min > 6h 上限

    cur = client.get("/api/v1/timer-sessions/current", headers=HDR).json()
    assert cur["restore"]["needsVerdict"] is True
    assert cur["restore"]["suggestedMinutes"] == 360

    assert _finish(sid).status_code == 400

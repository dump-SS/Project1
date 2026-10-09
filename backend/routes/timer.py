"""/timer-sessions 系列（D30 / D31 / D32 / #14）。

**这一层解决的根本问题**：现状 `/study-timer` 的上下文全靠 react-router 的
`navigate(state)` 传参，刷新或直链进来就丢任务、丢时长、丢 planId。
目标态 §3.6 定的口径是「**服务端持久化进行中的计时会话，前端仅是视图**」——
所以本模块是"专注态的唯一真相源"，前端回来只需 `GET /current` 按 mode 恢复。

四条口径（都来自目标态，不是本模块自创）：

1. **只留「结束」一个出口，不做挂起**（§3.6）——退出专注 = 结束 → 收尾，
   目的是不给"僵尸计时"留合法通道。
2. **双模式按 mode 分支恢复**（D30）：countdown 算剩余、countup 算累计。
3. **有效时长 ≠ 墙上时长**（D31）：倒计时 `min(经过, target)`；
   正计时异常时**必须用户核实**（裁决卡），不自动记账。
4. **一会话内分段，不允许并行计时**（#14）：切任务开新段，结束只走一次收尾。

僵尸判定的具体规则（目标态只给了方向，数值是本模块定的，均可调）：
- **断连**：距最近心跳 > `_HEARTBEAT_STALE_MINUTES`；
- **超上限**：countup 累计 > `_COUNTUP_MAX_MINUTES`，或 countdown 到点后又拖了
  > `_COUNTDOWN_GRACE_MINUTES` 仍未收尾。
命中任一条 → `needsVerdict=true`，前端弹裁决卡，**不得自动记账**。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.plan import PlanTask as PlanTaskORM
from models.timer import TimerSegment as TimerSegmentORM
from models.timer import TimerSession as TimerSessionORM
from record_service import persist_record
from schemas.learning_record import LearningRecordCreated, RecordBehavior, RecordInput
from schemas.timer import (
    TimerCurrent,
    TimerDiscarded,
    TimerFinish,
    TimerRestore,
    TimerSegment,
    TimerSegmentStart,
    TimerSession,
    TimerSessionStart,
)
from schemas.user import User
from state_calculator import gen_id
from .deps import current_user

router = APIRouter(prefix="/timer-sessions", tags=["专注计时"])

# ---------- 僵尸判定参数（可调） ----------

# 正计时上限：超过即判异常（正计时没有"到点"兜底，是僵尸重灾区）
_COUNTUP_MAX_MINUTES = 360
# 心跳落后多久算断连（前端定时上报心跳；关页面/合盖后不再上报）
_HEARTBEAT_STALE_MINUTES = 30
# 倒计时到点后又拖多久仍未收尾算异常
_COUNTDOWN_GRACE_MINUTES = 30

# 学习记录时长上下限（契约 RecordInput.durationMinutes 1-600）
_MIN_DURATION_MINUTES = 1
_MAX_DURATION_MINUTES = 600


def _utcnow() -> datetime:
    """naive UTC —— 与库内 `func.now()`（SQLite CURRENT_TIMESTAMP，UTC 无时区）保持同一口径。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _elapsed_seconds(row: TimerSessionORM, now: datetime) -> int:
    return max(0, int((now - row.started_at).total_seconds()))


def _is_anomalous(row: TimerSessionORM, now: datetime) -> bool:
    """是否判定为异常会话（需用户裁决，不自动记账）。"""
    last_seen = row.last_heartbeat_at or row.started_at
    if (now - last_seen).total_seconds() > _HEARTBEAT_STALE_MINUTES * 60:
        return True  # 断连

    elapsed = _elapsed_seconds(row, now)
    if row.mode == "countup":
        return elapsed > _COUNTUP_MAX_MINUTES * 60
    target = (row.target_minutes or 0) * 60
    return elapsed > target + _COUNTDOWN_GRACE_MINUTES * 60


def _build_restore(row: TimerSessionORM, now: datetime) -> TimerRestore:
    """按 mode 分支算恢复视图（D30）。"""
    elapsed = _elapsed_seconds(row, now)
    anomalous = _is_anomalous(row, now)

    if row.mode == "countdown":
        target = (row.target_minutes or 0) * 60
        # 剩余可以是负数（≤0 = 已到点）；不在这里截断，让前端知道"超了多少"
        remaining = target - elapsed
        return TimerRestore.model_validate(
            {
                "sessionId": row.id,
                "mode": row.mode,
                "remainingSeconds": remaining,
                "needsVerdict": anomalous,
                # 倒计时封顶 target（§3.6：到点后仍未结束 → 时长封顶 target）
                "suggestedMinutes": row.target_minutes,
            }
        )

    # countup：无到点，累计即 elapsed
    return TimerRestore.model_validate(
        {
            "sessionId": row.id,
            "mode": row.mode,
            "elapsedSeconds": elapsed,
            "needsVerdict": anomalous,
            # 截断点：异常时"保留按 X 记"的预填值，取上限与实际的较小者
            "suggestedMinutes": max(
                _MIN_DURATION_MINUTES,
                min(elapsed // 60, _COUNTUP_MAX_MINUTES) or _MIN_DURATION_MINUTES,
            ),
        }
    )


def _effective_minutes(row: TimerSessionORM, now: datetime) -> int:
    """有效时长（分钟）——D31：倒计时封顶 target，正计时按实际。"""
    elapsed = _elapsed_seconds(row, now)
    if row.mode == "countdown":
        elapsed = min(elapsed, (row.target_minutes or 0) * 60)
    minutes = elapsed // 60
    return max(_MIN_DURATION_MINUTES, min(minutes, _MAX_DURATION_MINUTES))


def _segments(db: Session, session_id: str) -> list[TimerSegmentORM]:
    return list(
        db.execute(
            select(TimerSegmentORM)
            .where(TimerSegmentORM.session_id == session_id)
            .order_by(TimerSegmentORM.started_at.asc(), TimerSegmentORM.id.asc())
        ).scalars().all()
    )


def _orm_to_session(row: TimerSessionORM, segments: list[TimerSegmentORM]) -> dict:
    return {
        "sessionId": row.id,
        "mode": row.mode,
        "startedAt": row.started_at,
        "targetMinutes": row.target_minutes,
        "planId": row.plan_id,
        "taskId": row.task_id,
        "subject": row.subject or "other",
        "status": row.status,
        "endedAt": row.ended_at,
        "effectiveSeconds": row.effective_seconds,
        "lastHeartbeatAt": row.last_heartbeat_at,
        "segments": [
            {
                "segmentId": s.id,
                "taskId": s.task_id,
                "startedAt": s.started_at,
                "endedAt": s.ended_at,
                "seconds": s.seconds,
            }
            for s in segments
        ],
        "createdAt": row.created_at,
    }


def _get_running(db: Session, user_id: str) -> TimerSessionORM | None:
    return db.execute(
        select(TimerSessionORM)
        .where(
            TimerSessionORM.user_id == user_id,
            TimerSessionORM.status == "running",
        )
        .order_by(TimerSessionORM.started_at.desc())
        .limit(1)
    ).scalars().first()


def _get_owned(db: Session, user_id: str, session_id: str) -> TimerSessionORM:
    row = db.get(TimerSessionORM, session_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "计时会话不存在"},
        )
    return row


def _require_running(row: TimerSessionORM) -> None:
    if row.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": f"该计时会话已{'结束' if row.status == 'finished' else '被丢弃'}，不能再操作",
            },
        )


def _close_open_segment(db: Session, row: TimerSessionORM, now: datetime) -> None:
    """关闭该会话最后一段（若还没关）。"""
    open_seg = db.execute(
        select(TimerSegmentORM)
        .where(
            TimerSegmentORM.session_id == row.id,
            TimerSegmentORM.ended_at.is_(None),
        )
        .order_by(TimerSegmentORM.started_at.desc())
        .limit(1)
    ).scalars().first()
    if open_seg is not None:
        open_seg.ended_at = now
        open_seg.seconds = max(0, int((now - open_seg.started_at).total_seconds()))


def _derive_subject(db: Session, user_id: str, task_id: str | None, explicit) -> str:
    """学科：显式传入优先；否则从计划任务推导；再否则 other。

    必须保证非空——契约 TimerSession.subject 是必填的 `$ref Subject`，
    而 ORM 列可空。这里补上，避免序列化时炸。
    """
    if explicit is not None:
        return explicit.value
    if task_id:
        task = db.get(PlanTaskORM, task_id)
        if task is not None and task.user_id == user_id:
            return task.subject
    return "other"


@router.post("", response_model=TimerSession, status_code=status.HTTP_201_CREATED, summary="开始计时")
def start_timer_session(
    body: TimerSessionStart,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerSession:
    """开始一次计时会话。

    **已有进行中会话时返回 409**，不静默接管、也不静默丢弃：
    产品上"专注中"同时只能有一个，用户必须先对上一个会话做出处置
    （继续 / 结束收尾 / 裁决丢弃）——否则会出现两段并行计时，
    或者用户的学习时长被系统悄悄丢掉。
    """
    existing = _get_running(db, _user.user_id)
    if existing is not None:
        restore = _build_restore(existing, _utcnow())
        hint = "该会话看起来异常，请先做恢复裁决" if restore.needs_verdict else "请先结束当前会话"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": f"已有进行中的计时会话（{existing.id}），{hint}",
            },
        )

    if body.mode == "countdown" and body.target_minutes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "倒计时模式必须提供目标时长",
                "field": "targetMinutes",
            },
        )

    now = _utcnow()
    session_id = gen_id("ts")
    row = TimerSessionORM(
        id=session_id,
        user_id=_user.user_id,
        mode=body.mode.value,
        started_at=now,
        # countup 不存 target（契约：countup 为 null），传了也忽略而不是报错
        target_minutes=body.target_minutes if body.mode == "countdown" else None,
        plan_id=body.plan_id,
        task_id=body.task_id,
        subject=_derive_subject(db, _user.user_id, body.task_id, body.subject),
        status="running",
        last_heartbeat_at=now,
    )
    db.add(row)
    # 第一段：从会话开始就属于会话的 task（#14 分段口径统一）
    db.add(
        TimerSegmentORM(
            id=gen_id("seg"),
            session_id=session_id,
            user_id=_user.user_id,
            task_id=body.task_id,
            started_at=now,
        )
    )
    db.commit()
    db.refresh(row)

    return TimerSession.model_validate(_orm_to_session(row, _segments(db, session_id)))


@router.get("/current", response_model=TimerCurrent, summary="当前计时会话（恢复视图）")
def get_current_timer_session(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerCurrent:
    """前端进计时页 / 刷新 / 换设备回来时调用。

    `active=false` 是正常流程（用户没在计时），不是错误。
    `restore.needsVerdict=true` 时必须先弹恢复裁决卡，不得自动记账。
    """
    row = _get_running(db, _user.user_id)
    if row is None:
        return TimerCurrent.model_validate({"active": False, "session": None, "restore": None})

    restore = _build_restore(row, _utcnow())
    return TimerCurrent.model_validate(
        {
            "active": True,
            "session": _orm_to_session(row, _segments(db, row.id)),
            "restore": restore.model_dump(by_alias=True),
        }
    )


@router.get("/{session_id}", response_model=TimerSession, summary="计时会话详情")
def get_timer_session(
    session_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerSession:
    row = _get_owned(db, _user.user_id, session_id)
    return TimerSession.model_validate(_orm_to_session(row, _segments(db, row.id)))


@router.post("/{session_id}/heartbeat", response_model=TimerSession, summary="上报心跳")
def heartbeat(
    session_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerSession:
    """刷新 `last_heartbeat_at` —— 僵尸判定与「异常会话」识别的唯一依据。

    前端应定时上报（并在每次用户交互时顺带上报）。不刷新心跳的后果不是报错，
    而是**下一次回来会被判成异常会话、要求用户裁决**——所以宁可多报。
    """
    row = _get_owned(db, _user.user_id, session_id)
    _require_running(row)

    now = _utcnow()
    row.last_heartbeat_at = now
    db.commit()
    db.refresh(row)
    return TimerSession.model_validate(_orm_to_session(row, _segments(db, session_id)))


@router.post(
    "/{session_id}/segments",
    response_model=TimerSegment,
    status_code=status.HTTP_201_CREATED,
    summary="切换任务（开新的一段）",
)
def switch_task(
    session_id: str,
    body: TimerSegmentStart,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerSegment:
    """#14：一个会话内分段，每段标注任务；**不允许并行计时**，所以只能是"换段"。

    旧段在切换瞬间关闭并结算秒数，新段从此刻开始。结束仍只走一次收尾。
    """
    row = _get_owned(db, _user.user_id, session_id)
    _require_running(row)

    now = _utcnow()
    _close_open_segment(db, row, now)

    seg = TimerSegmentORM(
        id=gen_id("seg"),
        session_id=row.id,
        user_id=_user.user_id,
        task_id=body.task_id,
        started_at=now,
    )
    db.add(seg)
    # 会话的主任务跟着走：收尾时学习记录要挂到最后在做的那件事上
    row.task_id = body.task_id
    row.last_heartbeat_at = now
    if body.task_id:
        row.subject = _derive_subject(db, _user.user_id, body.task_id, None)
    db.commit()
    db.refresh(seg)

    return TimerSegment.model_validate(
        {
            "segmentId": seg.id,
            "taskId": seg.task_id,
            "startedAt": seg.started_at,
            "endedAt": seg.ended_at,
            "seconds": seg.seconds,
        }
    )


@router.post(
    "/{session_id}/finish",
    response_model=LearningRecordCreated,
    status_code=status.HTTP_201_CREATED,
    summary="结束计时并收尾（落学习记录）",
)
def finish_timer_session(
    session_id: str,
    body: TimerFinish,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordCreated:
    """结束会话 + 落学习记录，**一次原子动作**。

    为什么不在前端分两步（先结束会话、再 POST /learning-records）：
    两步之间失败会留下"会话结束了但没有记录"的黑洞，正是 D31 要消灭的僵尸形态。
    所以收尾与落记录必须同一个请求完成。

    有效时长口径：
    - 传了 `durationMinutes` → **以它为准**（裁决卡「手动改时长」）；
    - countdown → `min(经过, target)`（到点后继续学也不多记，§3.6 封顶）；
    - countup → 实际经过；若已判异常且用户没给时长 → **400 要求先裁决**（不自动记账）。
    """
    row = _get_owned(db, _user.user_id, session_id)
    _require_running(row)

    now = _utcnow()

    if body.duration_minutes is not None:
        duration = body.duration_minutes
    else:
        if _is_anomalous(row, now):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": "该计时会话已被判为异常（断连或超时），请先做恢复裁决并提供时长，"
                               "或丢弃该会话",
                    "field": "durationMinutes",
                },
            )
        duration = _effective_minutes(row, now)

    row.status = "finished"
    row.ended_at = now
    row.effective_seconds = duration * 60
    row.last_heartbeat_at = now
    _close_open_segment(db, row, now)
    db.commit()

    record_body = RecordInput(
        subject=row.subject or "other",
        started_at=row.started_at,
        duration_minutes=duration,
        plan_task_id=row.task_id,
        behavior=RecordBehavior(completion=body.completion, accuracy=None),
        self_report=body.self_report,
        note=body.note,
        skip_recommendation=body.skip_recommendation,
    )
    return LearningRecordCreated.model_validate(
        persist_record(db, _user.user_id, record_body, background_tasks)
    )


@router.delete("/{session_id}", response_model=TimerDiscarded, summary="丢弃会话（裁决卡「丢弃」）")
def discard_timer_session(
    session_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TimerDiscarded:
    """裁决卡的「丢弃」：会话标记为 abandoned，**不产生任何学习记录**。

    这是 D31 验收里「僵尸会话不产生记录」的落点——宁可少记一次，
    也不要凭空造一段没发生过的学习时长。
    """
    row = _get_owned(db, _user.user_id, session_id)
    _require_running(row)

    now = _utcnow()
    row.status = "abandoned"
    row.ended_at = now
    # 明确不写 effective_seconds：没有可信时长，就不留一个会被误读的数字
    row.effective_seconds = None
    _close_open_segment(db, row, now)
    db.commit()

    return TimerDiscarded.model_validate({"discarded": True, "sessionId": session_id})

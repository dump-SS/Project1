"""学习记录落库编排（C 板块内部共享层）。

**为什么单独成模块**：落一条学习记录不只是 INSERT，而是三件连带动作：

1. 同步关联计划任务的状态（PRD 5.3：计划完成计数实时反映）；
2. 用 state_engine 重算该学科的状态快照（同步，事务内）；
3. 落一条 `pending` 建议并挂后台生成（PRD 6.4 异步语义）。

这三步在**「手动提交记录」与「计时收尾」两条入口上必须完全一致**——
否则同一段学习从计时页结束和从表单提交，会算出两个不同的状态分。
故抽成本模块，由 `routes/learning_record.py`（提交 / 回写）与
`routes/timer.py`（计时收尾）共用。

职责边界：
- 只做编排，**不写任何计算公式**（公式全在 `state_engine/`）；
- **不做权限校验**（调用方已用 `current_user` 校验过），也不抛 HTTPException；
- 只认 openapi 的 `RecordInput` 形状，调用方负责把计时会话翻译成它。

与 `routes/assessment.py` 的关系：那边只读窗口做展示，**不落快照**；
快照只在"记录发生写入"时落库（本模块的 `recompute_snapshot` 是唯一落点）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_suggestion import run_recommendation_generation
from models.assessment import AssessmentSnapshot as AssessmentSnapshotORM
from models.learning_record import LearningRecord as LearningRecordORM
from models.recommendation import Recommendation as RecommendationORM
from models.weight import UserWeightConfig
from state_engine.types import WeightConfig
from schemas.learning_record import RecordInput
from state_calculator import (
    compute_window_for_records,
    gen_id,
    orm_record_to_engine_input,
    window_to_snapshot_payload,
)

__all__ = [
    "as_utc_iso",
    "window_rows",
    "get_user_weights",
    "recompute_snapshot",
    "persist_record",
    "WINDOW_SIZE",
]

# 状态窗口大小（PRD 5.2：滑动窗口 7 条）
WINDOW_SIZE = 7


def as_utc_iso(dt: datetime) -> str:
    """把数据库取出的 naive datetime 当作 UTC 时刻，输出带 `Z` 后缀的 ISO 字符串。

    SQLite 没有原生时区列，存的是按 UTC 字面量（如 10:30:00）；
    不加后缀前端 dayjs 会按本地时区（UTC+8）解析，导致「10:30」误显示为实际时间 18:30。
    显式加 Z 让 dayjs 正确识别 UTC，再 format 到本地时区展示。
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def window_rows(
    db: Session, user_id: str, subject: str, limit: int = WINDOW_SIZE
) -> list[LearningRecordORM]:
    """该用户该学科最近 limit 条记录，按 started_at 时间正序返回。

    排序必须确定：只按 started_at 排序时，同一时间戳的多条记录顺序不确定，
    reversed() 后窗口可能整体颠倒，使线性回归斜率符号反转、趋势判定出错
    （批量导入或同一秒内多次提交会踩到）。故追加 created_at + id 作为稳定次序键。
    """
    rows = db.execute(
        select(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.subject == subject,
        )
        .order_by(
            LearningRecordORM.started_at.desc(),
            LearningRecordORM.created_at.desc(),
            LearningRecordORM.id.desc(),
        )
        .limit(limit)
    ).scalars().all()
    return list(reversed(rows))  # 时间正序


def get_user_weights(db: Session, user_id: str) -> WeightConfig:
    """读用户级权重表（UserWeightConfig，PRD 5.2 硬约束：权重不写死在代码里）。
    无配置时返回默认等权（α=β=0.5，子项 1/3，与 PRD 初始值一致）。
    """
    cfg = db.get(UserWeightConfig, user_id)
    if cfg is None:
        return WeightConfig()  # 默认等权
    return WeightConfig(
        alpha=cfg.alpha, beta=cfg.beta,
        w1=cfg.w1, w2=cfg.w2, w3=cfg.w3,
        w4=cfg.w4, w5=cfg.w5, w6=cfg.w6,
    )


def recompute_snapshot(
    db: Session, user_id: str, subject: str, trigger_record_id: str | None
) -> dict:
    """重算窗口（读最近 7 条），必要时落库快照，返回 camelCase snapshot dict。

    `data_sufficient=False` 时**不落库**（契约：assessmentId 为 null），
    避免冷启动期堆一串无意义的 insufficient_data 快照。
    """
    rows = window_rows(db, user_id, subject)
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]

    # 权重从用户级权重表读（PRD 5.2：权重存后台配置与用户级权重表）
    weights = get_user_weights(db, user_id)
    window = compute_window_for_records(engine_inputs, weights=weights)

    if window.data_sufficient:
        snapshot_id = gen_id("a")
        db.add(
            AssessmentSnapshotORM(
                id=snapshot_id,
                user_id=user_id,
                subject=subject,
                window_score=window.window_score or 0.0,
                trend=window.trend.value if window.trend else "flat",
                state_label=window.state_label.value,
                data_sufficient=True,
                record_count=window.record_count,
                based_on_record_ids=json.dumps([r.id for r in rows]),
                based_on_signals=json.dumps(window.signals),
                trigger_record_id=trigger_record_id,
            )
        )
        db.commit()
        return window_to_snapshot_payload(window, subject, snapshot_id)
    return window_to_snapshot_payload(window, subject, None)


def _sync_plan_task(db: Session, user_id: str, plan_task_id: str, completion: str) -> None:
    """关联计划任务时同步任务状态（PRD 5.3：计划完成计数应实时反映）。

    只改状态，不动 `user_adjusted`——那是"用户手动调整过算法建议"的信号，
    由用户在任务卡上的显式操作（PATCH /plans/{id}/tasks/{id}）标记，
    记录提交带来的自动同步不算。
    """
    from models.plan import PlanTask as PlanTaskORM

    task = db.get(PlanTaskORM, plan_task_id)
    if task is not None and task.user_id == user_id:
        task.status = completion
        db.commit()


def persist_record(
    db: Session,
    user_id: str,
    body: RecordInput,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """落一条学习记录 + 三件连带动作，返回 `LearningRecordCreated` 形状的 dict。

    `background_tasks` 为 None 时**不生成建议**（等价于 skipRecommendation=true）——
    用于"补记历史记录"这类不需要即时建议的场景。
    """
    record_id = gen_id("r")

    db.add(
        LearningRecordORM(
            id=record_id,
            user_id=user_id,
            subject=body.subject.value,
            started_at=body.started_at,
            duration_minutes=body.duration_minutes,
            plan_task_id=body.plan_task_id,
            behavior_completion=body.behavior.completion.value,
            behavior_accuracy=body.behavior.accuracy,
            behavior_interruptions=body.behavior.interruptions or 0,
            behavior_blur_count=body.behavior.blur_count,
            self_report_focus=body.self_report.focus,
            self_report_fatigue=body.self_report.fatigue,
            self_report_emotion=body.self_report.emotion.value,
            self_report_difficulty_feel=body.self_report.difficulty_feel.value,
            note=body.note,
            skip_recommendation=bool(body.skip_recommendation),
        )
    )
    db.commit()

    if body.plan_task_id:
        _sync_plan_task(db, user_id, body.plan_task_id, body.behavior.completion.value)

    assessment = recompute_snapshot(db, user_id, body.subject.value, record_id)

    recommendation = None
    if not body.skip_recommendation and background_tasks is not None:
        # 必须真实插入 pending 行：前端会拿 recommendationId 轮询 GET /recommendations/{id}。
        # 之前只返回随机 id、不落 ORM，轮询永远拿不到对应资源。
        recommendation_id = gen_id("rec")
        db.add(
            RecommendationORM(
                id=recommendation_id,
                user_id=user_id,
                scene="post_session",
                subject=body.subject.value,
                generation_status="pending",
                based_on_assessment_id=assessment.get("assessmentId"),
                based_on_record_id=record_id,
                based_on_state_label=assessment["stateLabel"],
                record_id=record_id,
            )
        )
        db.commit()

        # PRD 6.4 异步语义：LLM 调用挂后台（响应发出后执行），POST 立即返回
        # pending 句柄。后台任务自开 session（请求级 session 在响应后被
        # get_db 关闭，不可复用）。生成中轮询读到 items=null（契约 0.3）。
        background_tasks.add_task(
            run_recommendation_generation,
            recommendation_id, user_id, "post_session",
            body.subject.value, record_id,
        )
        recommendation = {"recommendationId": recommendation_id, "status": "pending"}

    # PRD 5.2 第 4 点：每次学习记录后异步检查是否需要调权（按周期/记录数阈值触发，
    # 不会每次记录都调）。挂后台任务，不阻塞响应。
    if background_tasks is not None:
        from weight_tuning import run_weight_tuning

        background_tasks.add_task(run_weight_tuning, user_id)

    created_at = db.execute(
        select(LearningRecordORM.created_at).where(LearningRecordORM.id == record_id)
    ).scalar_one()

    return {
        "recordId": record_id,
        "subject": body.subject.value,
        "startedAt": as_utc_iso(body.started_at),
        "durationMinutes": body.duration_minutes,
        "planTaskId": body.plan_task_id,
        "behavior": {
            "completion": body.behavior.completion.value,
            "accuracy": body.behavior.accuracy,
            "interruptions": body.behavior.interruptions or 0,
            "blurCount": body.behavior.blur_count,
        },
        "selfReport": {
            "focus": body.self_report.focus,
            "fatigue": body.self_report.fatigue,
            "emotion": body.self_report.emotion.value,
            "difficultyFeel": body.self_report.difficulty_feel.value,
        },
        "note": body.note,
        "assessment": assessment,
        "recommendation": recommendation,
        "createdAt": as_utc_iso(created_at),
    }


def record_orm_to_payload(row: LearningRecordORM) -> dict:
    """ORM 行 → `LearningRecord` 形状（列表 / 回写响应用）。"""
    return {
        "recordId": row.id,
        "subject": row.subject,
        "startedAt": as_utc_iso(row.started_at),
        "durationMinutes": row.duration_minutes,
        "planTaskId": row.plan_task_id,
        "behavior": {
            "completion": row.behavior_completion,
            "accuracy": row.behavior_accuracy,
            "interruptions": row.behavior_interruptions,
            "blurCount": row.behavior_blur_count,
        },
        "selfReport": {
            "focus": row.self_report_focus,
            "fatigue": row.self_report_fatigue,
            "emotion": row.self_report_emotion,
            "difficultyFeel": row.self_report_difficulty_feel,
        },
        "note": row.note,
        "createdAt": row.created_at.isoformat(),
    }


def count_records(db: Session, user_id: str, subject: str) -> int:
    """该用户该学科的记录总数（窗口外也有记录时，用于判断"回写是否改变了窗口"）。"""
    return db.execute(
        select(func.count())
        .select_from(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.subject == subject,
        )
    ).scalar_one()

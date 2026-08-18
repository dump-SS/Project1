"""/learning-records 系列。

阶段 3（已接入）：POST 落库后用 state_engine 同步重算状态快照，
并自动创建建议任务（pending）触发 ai_suggestion 同步生成。
GET 列表读库，DELETE 删除后即时重算。计算公式在 state_engine 内。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _as_utc_iso(dt: datetime) -> str:
    """把数据库取出的 naive datetime 当作 UTC 时刻，输出带 `Z` 后缀的 ISO 字符串。

    SQLite 没有原生时区列，存的是按 UTC 字面量（如 10:30:00）；
    不加后缀前端 dayjs 会按本地时区（UTC+8）解析，导致「10:30」误显示为实际时间 18:30。
    显式加 Z 让 dayjs 正确识别 UTC，再 format 到本地时区展示。
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

from ai_suggestion import run_recommendation_generation
from database import get_db
from models.assessment import AssessmentSnapshot as AssessmentSnapshotORM
from models.learning_record import LearningRecord as LearningRecordORM
from models.recommendation import Recommendation as RecommendationORM
from models.weight import UserWeightConfig
from state_engine.types import WeightConfig
from weight_tuning import run_weight_tuning
from schemas.learning_record import (
    LearningRecordCreated,
    LearningRecordDeleted,
    LearningRecordList,
    RecordInput,
)
from schemas.user import User
from state_calculator import (
    compute_window_for_records,
    gen_id,
    orm_record_to_engine_input,
    window_to_snapshot_payload,
)
from .deps import current_user

router = APIRouter(prefix="/learning-records", tags=["学习记录"])


def _window_rows(
    db: Session, user_id: str, subject: str, limit: int = 7
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


def _get_user_weights(db: Session, user_id: str) -> WeightConfig:
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


def _recompute_snapshot(
    db: Session, user_id: str, subject: str, trigger_record_id: str | None
) -> dict:
    """重算窗口（读最近 7 条），必要时落库快照，返回 camelCase snapshot dict。"""
    rows = _window_rows(db, user_id, subject)
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]

    # 权重从用户级权重表读（PRD 5.2：权重存后台配置与用户级权重表）
    weights = _get_user_weights(db, user_id)
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


@router.post(
    "",
    response_model=LearningRecordCreated,
    status_code=status.HTTP_201_CREATED,
    summary="提交学习记录（核心接口）③④",
)
def create_learning_record(
    body: RecordInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordCreated:
    """保存记录，同步用 state_engine 重算状态；建议生成挂后台（PRD 6.4），立即返回 pending 句柄。"""
    record_id = gen_id("r")

    db.add(
        LearningRecordORM(
            id=record_id,
            user_id=_user.user_id,
            subject=body.subject.value,
            started_at=body.started_at,
            duration_minutes=body.duration_minutes,
            plan_task_id=body.plan_task_id,
            behavior_completion=body.behavior.completion.value,
            behavior_accuracy=body.behavior.accuracy,
            behavior_interruptions=body.behavior.interruptions or 0,
            behavior_blur_count=body.behavior.blur_count or 0,
            self_report_focus=body.self_report.focus,
            self_report_fatigue=body.self_report.fatigue,
            self_report_emotion=body.self_report.emotion.value,
            self_report_difficulty_feel=body.self_report.difficulty_feel.value,
            note=body.note,
            skip_recommendation=bool(body.skip_recommendation),
        )
    )
    db.commit()

    # 提交学习记录时，若关联了计划任务，自动同步任务状态（PRD 5.3：计划完成计数应实时反映）
    if body.plan_task_id:
        from models.plan import PlanTask as PlanTaskORM
        task = db.get(PlanTaskORM, body.plan_task_id)
        if task is not None and task.user_id == _user.user_id:
            task.status = body.behavior.completion.value
            db.commit()

    assessment = _recompute_snapshot(db, _user.user_id, body.subject.value, record_id)

    recommendation = None
    if not body.skip_recommendation:
        # 必须真实插入 pending 行：前端会拿 recommendationId 轮询 GET /recommendations/{id}。
        # 之前只返回随机 id、不落 ORM，轮询永远拿不到对应资源。
        recommendation_id = gen_id("rec")
        db.add(
            RecommendationORM(
                id=recommendation_id,
                user_id=_user.user_id,
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
            recommendation_id, _user.user_id, "post_session",
            body.subject.value, record_id,
        )
        recommendation = {"recommendationId": recommendation_id, "status": "pending"}

    # PRD 5.2 第 4 点：每次学习记录后异步检查是否需要调权（按周期/记录数阈值触发，
    # 不会每次记录都调）。挂后台任务，不阻塞 POST 响应。
    background_tasks.add_task(run_weight_tuning, _user.user_id)

    return LearningRecordCreated.model_validate(
        {
            "recordId": record_id,
            "subject": body.subject.value,
            "startedAt": _as_utc_iso(body.started_at),
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
            "createdAt": _as_utc_iso(
                db.execute(
                    select(LearningRecordORM.created_at).where(LearningRecordORM.id == record_id)
                ).scalar_one()
            ),
        }
    )


@router.get("", response_model=LearningRecordList, summary="学习记录列表")
def list_learning_records(
    subject: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordList:
    query = select(LearningRecordORM).where(LearningRecordORM.user_id == _user.user_id)
    if subject:
        query = query.where(LearningRecordORM.subject == subject)
    if date_from:
        query = query.where(LearningRecordORM.started_at >= date_from)
    if date_to:
        query = query.where(LearningRecordORM.started_at <= date_to)

    # total 必须用和查询相同的过滤条件——之前只按 user 统计，
    # 带 subject/date 筛选时 total > len(items)，分页器会误以为还有更多页
    total_query = query.with_only_columns(func.count()).order_by(None)
    total = db.execute(total_query).scalar_one()

    query = query.order_by(LearningRecordORM.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(query).scalars().all()

    items = []
    for row in rows:
        items.append(
            {
                "recordId": row.id,
                "subject": row.subject,
                "startedAt": _as_utc_iso(row.started_at),
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
        )

    return LearningRecordList(
        items=items,
        pagination={"page": page, "pageSize": page_size, "total": total},
    )


@router.delete(
    "/{record_id}",
    response_model=LearningRecordDeleted,
    summary="删除学习记录并重算当前窗口",
)
def delete_learning_record(
    record_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordDeleted:
    row = db.get(LearningRecordORM, record_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "记录不存在"},
        )

    subject = row.subject
    db.delete(row)
    db.commit()

    assessment = _recompute_snapshot(db, _user.user_id, subject, record_id)

    return LearningRecordDeleted.model_validate(
        {
            "deleted": True,
            "recordId": record_id,
            "recalculatedAssessment": assessment,
        }
    )
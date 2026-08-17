"""/learning-records 系列。

阶段 3（已接入）：POST 落库后用 state_engine 同步重算状态快照，
并自动创建建议任务（pending）触发 ai_suggestion 同步生成。
GET 列表读库，DELETE 删除后即时重算。计算公式在 state_engine 内。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_suggestion import run_recommendation_generation
from database import get_db
from models.assessment import AssessmentSnapshot as AssessmentSnapshotORM
from models.learning_record import LearningRecord as LearningRecordORM
from models.recommendation import Recommendation as RecommendationORM
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


def _recompute_snapshot(
    db: Session, user_id: str, subject: str, trigger_record_id: str | None
) -> dict:
    """重算窗口（读最近 7 条），必要时落库快照，返回 camelCase snapshot dict。"""
    rows = _window_rows(db, user_id, subject)
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]
    window = compute_window_for_records(engine_inputs)

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

    return LearningRecordCreated.model_validate(
        {
            "recordId": record_id,
            "subject": body.subject.value,
            "startedAt": body.started_at.isoformat(),
            "durationMinutes": body.duration_minutes,
            "planTaskId": body.plan_task_id,
            "behavior": {
                "completion": body.behavior.completion.value,
                "accuracy": body.behavior.accuracy,
                "interruptions": body.behavior.interruptions or 0,
                "blurCount": body.behavior.blur_count or 0,
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
            "createdAt": db.execute(
                select(LearningRecordORM.created_at).where(LearningRecordORM.id == record_id)
            ).scalar_one().isoformat(),
        }
    )


@router.get("", response_model=LearningRecordList, summary="学习记录列表")
def list_learning_records(
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
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
    query = query.order_by(LearningRecordORM.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(query).scalars().all()

    total = db.execute(
        select(LearningRecordORM).where(LearningRecordORM.user_id == _user.user_id)
    ).scalars().all()

    items = []
    for row in rows:
        items.append(
            {
                "recordId": row.id,
                "subject": row.subject,
                "startedAt": row.started_at.isoformat(),
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
        pagination={"page": page, "pageSize": page_size, "total": len(total)},
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
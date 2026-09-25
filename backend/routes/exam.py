"""/exams 系列（D49 考试独立实体）。

**为什么考试要独立成实体**（目标态 §4.9.1）：
考试不是"目标的一种"——目标表达意愿（"这次想考到 120"），考试表达事实（"11/05 期中，考了 118"）。
两者一旦混在一张表里，就会出现"同一个目标既想表达意愿又想表达结果"的平行体系。
所以：`exams` 存事实，`goals.exam_id + target_score` 存意愿，Goal 引用考试。

**成绩回填**（`PATCH /exams/{examId}` 传 score）：
分数是唯一能把「自评」与「实际」对上的客观数据。回填后本模块会**自动生成一条
`source=exam` 的学习记录**（D49：成绩喂状态评估），并遵守三条纪律：

1. **不编自评**：考试成绩没有自评（没人会为一次期中考试填"专注度 4 分"），
   所以这条记录的 `selfReport` 整段为空，交给 state_engine 走"自评不可用 → 只按行为子分计"
   的降级路径。绝不为了凑字段编数据（D34）。
2. **不编时长**：记录的学习时长必填，取值只有一处来源——`Exam.durationMinutes`（客观事实）。
   **没填时长就不生成记录**，宁可少一条记录，也不编一个时长。
3. **幂等 + 不打扰**：同一场考试重复回填只更新那一条记录，不会造出第二条；
   也不触发建议生成（补个分数不该推一条"学习建议"）。
"""

from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.exam import Exam as ExamORM
from models.goal import Goal as GoalORM
from models.learning_record import LearningRecord as LearningRecordORM
from record_service import persist_record, recompute_snapshot
from schemas.common import Pagination
from schemas.enums import Completion
from schemas.exam import Exam, ExamCreate, ExamDeleted, ExamList, ExamUpdate
from schemas.learning_record import RecordBehavior, RecordInput
from schemas.user import User
from state_calculator import gen_id
from .deps import current_user

router = APIRouter(prefix="/exams", tags=["考试"])


def _orm_to_exam(row: ExamORM) -> dict:
    return {
        "examId": row.id,
        "subject": row.subject,
        "name": row.name,
        "examDate": row.exam_date.isoformat(),
        "score": row.score,
        "fullScore": row.full_score,
        "durationMinutes": row.duration_minutes,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


def _check_score(score: float | None, full_score: float) -> None:
    """分数必须落在 [0, 满分]。超满分是录入错误，必须报错而不是截断。"""
    if score is not None and score > full_score:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"得分不能超过满分（{score} > {full_score}）",
                "field": "score",
            },
        )


def _get_owned_exam(db: Session, user_id: str, exam_id: str) -> ExamORM:
    row = db.get(ExamORM, exam_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "考试不存在"},
        )
    return row


def _sync_exam_record(db: Session, user_id: str, exam_row: ExamORM) -> str | None:
    """成绩回填 → 维护那条 `source=exam` 的学习记录（D49 喂状态评估）。

    返回记录 ID；未满足生成条件时返回 None。三条纪律见模块 docstring。

    幂等实现：以 `source_exam_id` 为键查已有记录——重复回填只更新，不新增。
    这很重要：用户发现分数填错了改一次，不该在状态窗口里多出一条记录。
    """
    if exam_row.score is None or not exam_row.duration_minutes:
        # 没分数（撤回回填）或没时长 → 不生成/不更新记录。
        # 若已有记录而用户撤回了分数，则把记录一并删掉（撤回就是撤回，不留半条）。
        existing = db.execute(
            select(LearningRecordORM).where(
                LearningRecordORM.user_id == user_id,
                LearningRecordORM.source_exam_id == exam_row.id,
            )
        ).scalars().first()
        if existing is not None and exam_row.score is None:
            db.delete(existing)
            db.commit()
            recompute_snapshot(db, user_id, exam_row.subject, existing.id)
        return None

    accuracy = exam_row.score / exam_row.full_score if exam_row.full_score else None
    # 考试只精确到日期，没有时刻。取当天 00:00 作为记录起点——不编一个"看起来像真的"的时刻。
    started_at = datetime.combine(exam_row.exam_date, time.min)

    existing = db.execute(
        select(LearningRecordORM).where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.source_exam_id == exam_row.id,
        )
    ).scalars().first()
    if existing is not None:
        existing.behavior_accuracy = accuracy
        existing.duration_minutes = exam_row.duration_minutes
        existing.started_at = started_at
        existing.subject = exam_row.subject
        db.commit()
        recompute_snapshot(db, user_id, exam_row.subject, existing.id)
        return existing.id

    payload = persist_record(
        db,
        user_id,
        RecordInput(
            subject=exam_row.subject,
            started_at=started_at,
            duration_minutes=exam_row.duration_minutes,
            behavior=RecordBehavior(completion=Completion.completed, accuracy=accuracy),
            self_report=None,  # ← 考试没有自评，整段留空（引擎按"自评不可用"降级）
            note=f"{exam_row.name} · 成绩回填",
            skip_recommendation=True,  # 补个分数不推"学习建议"
        ),
        background_tasks=None,
        source="exam",
        source_exam_id=exam_row.id,
    )
    return payload["recordId"]


@router.post("", response_model=Exam, status_code=status.HTTP_201_CREATED, summary="新建考试")
def create_exam(
    body: ExamCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Exam:
    _check_score(body.score, body.full_score)

    row = ExamORM(
        id=gen_id("e"),
        user_id=_user.user_id,
        subject=body.subject.value,
        name=body.name,
        exam_date=body.exam_date,
        score=body.score,
        full_score=body.full_score,
        duration_minutes=body.duration_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # 考后一次录入（创建时就带分数与时长）同样要喂状态评估
    if body.score is not None:
        _sync_exam_record(db, _user.user_id, row)

    return Exam.model_validate(_orm_to_exam(row))


@router.get("", response_model=ExamList, summary="考试列表")
def list_exams(
    subject: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ExamList:
    query = select(ExamORM).where(ExamORM.user_id == _user.user_id)
    if subject:
        query = query.where(ExamORM.subject == subject)
    if date_from:
        query = query.where(ExamORM.exam_date >= date_from)
    if date_to:
        query = query.where(ExamORM.exam_date <= date_to)

    total = db.execute(query.with_only_columns(func.count()).order_by(None)).scalar_one()

    rows = db.execute(
        query.order_by(ExamORM.exam_date.desc(), ExamORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    return ExamList(
        items=[Exam.model_validate(_orm_to_exam(r)) for r in rows],
        pagination=Pagination(page=page, pageSize=page_size, total=total),
    )


@router.get("/{exam_id}", response_model=Exam, summary="考试详情")
def get_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Exam:
    return Exam.model_validate(_orm_to_exam(_get_owned_exam(db, _user.user_id, exam_id)))


@router.patch("/{exam_id}", response_model=Exam, summary="更新考试 / 回填成绩")
def update_exam(
    exam_id: str,
    body: ExamUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> Exam:
    row = _get_owned_exam(db, _user.user_id, exam_id)
    provided = body.model_fields_set

    if "name" in provided and body.name is not None:
        row.name = body.name
    if "exam_date" in provided and body.exam_date is not None:
        row.exam_date = body.exam_date
    if "full_score" in provided and body.full_score is not None:
        row.full_score = body.full_score
    if "duration_minutes" in provided and body.duration_minutes is not None:
        row.duration_minutes = body.duration_minutes
    if "score" in provided:
        # 显式传 null = 撤回回填（比如发现分数填错了科目）
        _check_score(body.score, row.full_score)
        row.score = body.score

    db.commit()
    db.refresh(row)

    # 成绩变了 → 同步那条 source=exam 的学习记录（D49：喂状态评估）
    _sync_exam_record(db, _user.user_id, row)
    db.refresh(row)
    return Exam.model_validate(_orm_to_exam(row))


@router.delete("/{exam_id}", response_model=ExamDeleted, summary="删除考试")
def delete_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ExamDeleted:
    row = _get_owned_exam(db, _user.user_id, exam_id)

    # 被目标引用时拒绝删除：删掉会让 goal.exam_id 变悬空引用，
    # 而"目标指向一场不存在的考试"在界面上无法解释。让用户先解绑（PATCH /goals/{id}）。
    referencing = db.execute(
        select(func.count())
        .select_from(GoalORM)
        .where(GoalORM.exam_id == exam_id)
    ).scalar_one()
    if referencing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": f"该考试被 {referencing} 个目标引用，请先解除关联再删除",
            },
        )

    # 连带删掉这场考试生成的那条学习记录：它本来就是"这次考试"的产物，
    # 考试被删（录错了）而记录还在，会变成一条无源可查的孤立数据。
    generated = db.execute(
        select(LearningRecordORM).where(
            LearningRecordORM.user_id == _user.user_id,
            LearningRecordORM.source_exam_id == exam_id,
        )
    ).scalars().all()
    subject = row.subject
    for rec in generated:
        db.delete(rec)
    db.delete(row)
    db.commit()
    if generated:
        recompute_snapshot(db, _user.user_id, subject, None)

    return ExamDeleted.model_validate({"deleted": True, "examId": exam_id})

"""/exams 系列（D49 考试独立实体）。

**为什么考试要独立成实体**（目标态 §4.9.1）：
考试不是"目标的一种"——目标表达意愿（"这次想考到 120"），考试表达事实（"11/05 期中，考了 118"）。
两者一旦混在一张表里，就会出现"同一个目标既想表达意愿又想表达结果"的平行体系。
所以：`exams` 存事实，`goals.exam_id + target_score` 存意愿，Goal 引用考试。

**成绩回填**（`PATCH /exams/{examId}` 传 score）：
分数是唯一能把「自评」与「实际」对上的客观数据。回填后本模块保证：
- 校验分数不超满分（超了直接 400，不静默截断——静默截断会让用户以为系统算错了）；
- 关联目标能被读到 `scoreRate`（前端据此展示"目标 120 / 实际 118 / 满分 150"）。

⚠️ **尚未实现的一环**（已在 C→X0 需求单登记）：把成绩作为客观信号喂进状态评估与画像。
阻塞点是 `learning_records.self_report_*` 四列 NOT NULL —— 考试没有"专注度/疲劳度"自评，
自动生成记录会造数（违反 D34「不造数」）。等 X0 放开可空后再接。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.exam import Exam as ExamORM
from models.goal import Goal as GoalORM
from schemas.common import Pagination
from schemas.exam import Exam, ExamCreate, ExamDeleted, ExamList, ExamUpdate
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
    )
    db.add(row)
    db.commit()
    db.refresh(row)
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
    if "score" in provided:
        # 显式传 null = 撤回回填（比如发现分数填错了科目）
        _check_score(body.score, row.full_score)
        row.score = body.score

    db.commit()
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

    db.delete(row)
    db.commit()
    return ExamDeleted.model_validate({"deleted": True, "examId": exam_id})

"""板块二错题本 API（PRD 12.3.2，契约 v1.5 错题本 5 条 + 复习 1 条）。

- GET    /error-book                    列表（subject/status 过滤，软删过滤）
- POST   /error-book                    录入（原文只本地；录入前敏感词检测；pointIds 直接关联）
- GET    /error-book/{errorId}          详情
- PATCH  /error-book/{errorId}          改错因/状态/关联点
- DELETE /error-book/{errorId}          软删（deleted_at）
- POST   /error-book/{errorId}/review   复习（recallCorrect → 更新间隔 + review log）

合规：rawText/studentAnswer/correctAnswer/errorNote 属 knowledge_raw，
永不出域；EgressGuard 黑名单独立校验，本模块不调用云端 LLM。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.knowledge import (
    ErrorPoint as ErrorPointORM,
    ErrorRecord as ErrorRecordORM,
    KnowledgePoint as KnowledgePointORM,
    ReviewLog as ReviewLogORM,
)
from privacy_filter import contains_sensitive_info
from schemas.error_book import (
    ErrorBookList,
    ErrorRecord,
    ErrorRecordCreate,
    ErrorRecordDeleted,
    ErrorRecordUpdate,
    LinkedPoint,
    ReviewResult,
    ReviewSubmit,
)
from schemas.user import User
from .deps import current_user

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/error-book", tags=["错题本"])

MAX_RAW_LEN = 4000  # PRD 12.3.2：raw_text ≤4000 字

# 艾宾浩斯间隔（回忆正确依次进入下一档；错误回到 1 天）
REVIEW_INTERVALS = [1, 2, 4, 7, 15]


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _to_item(row: ErrorRecordORM, db: Session) -> dict:
    pts = db.execute(
        select(ErrorPointORM, KnowledgePointORM)
        .join(KnowledgePointORM, KnowledgePointORM.id == ErrorPointORM.point_id)
        .where(ErrorPointORM.error_id == row.id)
    ).all()
    return {
        "errorId": row.id,
        "subject": row.subject,
        "rawText": row.raw_text,
        "studentAnswer": row.student_answer,
        "correctAnswer": row.correct_answer,
        "errorType": row.error_type,
        "errorNote": row.error_note,
        "status": row.status,
        "points": [
            LinkedPoint.model_validate(
                {"pointId": p.id, "name": p.name, "confidence": e.confidence}
            ).model_dump(by_alias=True)
            for e, p in pts
        ],
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "lastReviewedAt": row.last_reviewed_at.isoformat() if row.last_reviewed_at else None,
    }


def _check_sensitive(payload: ErrorRecordCreate) -> None:
    """录入前敏感词检测（PRD 12.10 / gap §3.2）：命中阻断，不静默脱敏。"""
    for field, value in (
        ("rawText", payload.raw_text),
        ("errorNote", payload.error_note),
    ):
        if value:
            hit, names = contains_sensitive_info(value)
            if hit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "VALIDATION_FAILED",
                        "message": f"文本可能含敏感信息（{'、'.join(names)}），请去除后再提交",
                        "field": field,
                    },
                )


@router.get("", response_model=ErrorBookList, summary="错题列表")
def list_errors(
    subject: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorBookList:
    q = select(ErrorRecordORM).where(
        ErrorRecordORM.user_id == _user.user_id,
        ErrorRecordORM.deleted_at.is_(None),
    )
    if subject:
        q = q.where(ErrorRecordORM.subject == subject)
    if status_filter:
        q = q.where(ErrorRecordORM.status == status_filter)

    total = db.execute(
        select(func.count()).select_from(q.subquery())
    ).scalar_one()
    rows = db.execute(
        q.order_by(ErrorRecordORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return ErrorBookList(
        items=[ErrorRecord.model_validate(_to_item(r, db)) for r in rows],
        pagination={"page": page, "pageSize": page_size, "total": total},
    )


@router.post(
    "",
    response_model=ErrorRecord,
    status_code=status.HTTP_201_CREATED,
    summary="错题录入（原文不出域）",
)
def create_error(
    payload: ErrorRecordCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorRecord:
    if len(payload.raw_text) > MAX_RAW_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "KB_TEXT_TOO_LONG", "message": "错题文本过长，请精简到 4000 字以内", "field": "rawText"},
        )
    _check_sensitive(payload)

    err = ErrorRecordORM(
        id=_gen("err"),
        user_id=_user.user_id,
        subject=payload.subject,
        raw_text=payload.raw_text,
        student_answer=payload.student_answer,
        correct_answer=payload.correct_answer,
        error_type=payload.error_type,
        error_note=payload.error_note,
        status="open",
    )
    db.add(err)
    db.flush()

    for pid in payload.point_ids or []:
        if db.get(KnowledgePointORM, pid) is not None:
            db.add(ErrorPointORM(id=_gen("erp"), error_id=err.id, point_id=pid, confidence=1.0))

    db.commit()

    # 触发式 mastery 重算（PRD 12.3.4）：错题关联的点都要更新
    from .mastery import recompute_and_store
    for pid in payload.point_ids or []:
        recompute_and_store(db, _user.user_id, pid)
    db.commit()

    # 异步 embedding + 候选知识点匹配（v2.1-B6；embed off 时任务为空操作）
    background_tasks.add_task(_async_embed_error, err.id)

    return ErrorRecord.model_validate(_to_item(err, db))


def _async_embed_error(error_id: str) -> None:
    """后台任务：对错题原文做 embedding 并写 kb_embeddings 引用 + 向量索引。

    embed off / 失败均静默降级——录入已成功，匹配走 name_fuzzy，不阻断。
    """
    from database import SessionLocal
    from embedding_service import embed_text, embed_mode
    from models.knowledge import EmbeddingRef as EmbedRef

    db = SessionLocal()
    try:
        if embed_mode() == "off":
            return
        row = db.get(ErrorRecordORM, error_id)
        if row is None:
            return
        vec = embed_text(row.raw_text)
        if vec is None:
            return
        ref_id = _gen("ve")
        db.add(EmbedRef(
            vector_id=ref_id, ref_type="error", ref_id=error_id,
            model=embed_mode(), dim=len(vec),
        ))
        row.vector_id = ref_id
        db.commit()
        # 向量本体入本地 FAISS 索引（引用表不含向量，落盘才能检索）
        from vector_store import add as vector_add

        vector_add(vec, ref_id, "error", error_id, embed_mode(), len(vec))
    except Exception as e:  # noqa: BLE001
        logger.warning("[ERROR_BOOK] 异步 embedding 失败: %s", e)
    finally:
        db.close()


@router.get("/{error_id}", response_model=ErrorRecord, summary="错题详情")
def get_error(
    error_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorRecord:
    row = db.get(ErrorRecordORM, error_id)
    if row is None or row.user_id != _user.user_id or row.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "错题不存在"},
        )
    return ErrorRecord.model_validate(_to_item(row, db))


@router.patch("/{error_id}", response_model=ErrorRecord, summary="更新错题")
def update_error(
    error_id: str,
    payload: ErrorRecordUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorRecord:
    row = db.get(ErrorRecordORM, error_id)
    if row is None or row.user_id != _user.user_id or row.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "错题不存在"},
        )
    if payload.error_type is not None:
        row.error_type = payload.error_type
    if payload.error_note is not None:
        row.error_note = payload.error_note
    if payload.status is not None:
        if payload.status not in ("open", "resolved"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "VALIDATION_FAILED", "message": "status 仅支持 open/resolved", "field": "status"},
            )
        row.status = payload.status
    if payload.point_ids is not None:
        db.execute(ErrorPointORM.__table__.delete().where(ErrorPointORM.error_id == error_id))
        for pid in payload.point_ids:
            if db.get(KnowledgePointORM, pid) is not None:
                db.add(ErrorPointORM(id=_gen("erp"), error_id=error_id, point_id=pid, confidence=1.0))
    db.commit()

    from .mastery import recompute_and_store
    for ep in db.execute(
        select(ErrorPointORM.point_id).where(ErrorPointORM.error_id == error_id)
    ).all():
        recompute_and_store(db, _user.user_id, ep[0])
    db.commit()

    return ErrorRecord.model_validate(_to_item(row, db))


@router.delete("/{error_id}", response_model=ErrorRecordDeleted, summary="软删错题")
def delete_error(
    error_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorRecordDeleted:
    row = db.get(ErrorRecordORM, error_id)
    if row is None or row.user_id != _user.user_id or row.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "错题不存在"},
        )
    row.deleted_at = datetime.utcnow()
    db.commit()
    return ErrorRecordDeleted(deleted=True, error_id=error_id)


@router.post("/{error_id}/review", response_model=ReviewResult, summary="提交复习结果")
def review_error(
    error_id: str,
    payload: ReviewSubmit,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ReviewResult:
    """艾宾浩斯：正确 → 下一间隔档；错误 → 回到 1 天。写 review log 并更新 last_reviewed_at。"""
    row = db.get(ErrorRecordORM, error_id)
    if row is None or row.user_id != _user.user_id or row.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "错题不存在"},
        )

    last = db.execute(
        select(ReviewLogORM)
        .where(ReviewLogORM.error_id == error_id)
        .order_by(ReviewLogORM.reviewed_at.desc())
        .limit(1)
    ).scalars().first()

    if payload.recall_correct:
        # 找到当前 interval 在间隔序中的位置，进一档；首次从 1 天开始
        cur = last.interval_days if last else REVIEW_INTERVALS[0]
        idx = REVIEW_INTERVALS.index(cur) if cur in REVIEW_INTERVALS else 0
        next_interval = REVIEW_INTERVALS[min(idx + 1, len(REVIEW_INTERVALS) - 1)]
    else:
        next_interval = REVIEW_INTERVALS[0]

    log = ReviewLogORM(
        id=_gen("rvl"),
        error_id=error_id,
        user_id=_user.user_id,
        recall_correct=payload.recall_correct,
        interval_days=next_interval,
    )
    db.add(log)
    row.last_reviewed_at = datetime.utcnow()
    db.commit()

    # 触发式 mastery 重算（复习改变 recall/recency 因子）
    from .mastery import recompute_and_store
    for ep in db.execute(
        select(ErrorPointORM.point_id).where(ErrorPointORM.error_id == error_id)
    ).all():
        recompute_and_store(db, _user.user_id, ep[0])
    db.commit()

    next_at = (datetime.utcnow() + timedelta(days=next_interval)).date().isoformat()
    return ReviewResult(
        correct=payload.recall_correct,
        nextReviewAt=next_at,
        intervalDays=next_interval,
    )

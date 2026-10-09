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
    ERROR_CAUSES,
    ERROR_INTENTS,
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
        # D48 两正交维度：errorCause（结构化错因）/ intent（主观意图）
        # 无错因即 star 题——照样在题本里、照样复习，但不喂 mastery。
        "errorCause": row.error_cause,
        "intent": row.intent,
        "sourceExamId": row.source_exam_id,
    }


def _validate_dimensions(error_cause: str | None, intent: str | None) -> None:
    """校验 D48 两维度取值（契约 ErrorCause / ErrorIntent 枚举）。

    非法值直接 400，不静默丢弃——静默丢弃会让「用户以为存了错因、其实没存」，
    进而导致 mastery 少算样本，这种偏差事后极难排查。
    """
    if error_cause is not None and error_cause not in ERROR_CAUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"errorCause 取值非法，可选：{'、'.join(ERROR_CAUSES)}",
                "field": "errorCause",
            },
        )
    if intent is not None and intent not in ERROR_INTENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"intent 取值非法，可选：{'、'.join(ERROR_INTENTS)}",
                "field": "intent",
            },
        )


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
    error_cause: str | None = Query(None, alias="errorCause"),
    intent: str | None = Query(None, alias="intent"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ErrorBookList:
    """题本列表。D48 两维度可按错因 / 意图单独或组合筛选（两维度正交，组合是「且」）。"""
    if error_cause is not None and error_cause not in ERROR_CAUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"errorCause 取值非法，可选：{'、'.join(ERROR_CAUSES)}",
                "field": "errorCause",
            },
        )
    if intent is not None and intent not in ERROR_INTENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"intent 取值非法，可选：{'、'.join(ERROR_INTENTS)}",
                "field": "intent",
            },
        )

    q = select(ErrorRecordORM).where(
        ErrorRecordORM.user_id == _user.user_id,
        ErrorRecordORM.deleted_at.is_(None),
    )
    if subject:
        q = q.where(ErrorRecordORM.subject == subject)
    if status_filter:
        q = q.where(ErrorRecordORM.status == status_filter)
    if error_cause:
        q = q.where(ErrorRecordORM.error_cause == error_cause)
    if intent:
        q = q.where(ErrorRecordORM.intent == intent)

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
    _validate_dimensions(payload.error_cause, payload.intent)

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
        # D48 两正交维度 + D49 来源考试（sourceExamId 不校验考试是否存在——
        # exams 属 C 板块，跨板块不读别人的表；只存 ID，由 C 侧接口负责展示）
        error_cause=payload.error_cause,
        intent=payload.intent,
        source_exam_id=payload.source_exam_id,
    )
    db.add(err)
    db.flush()

    # 有错因才算「错题」：无错因（star 题）也要关联知识点，但不喂 mastery（D48）
    has_cause = payload.error_cause is not None

    for pid in payload.point_ids or []:
        if db.get(KnowledgePointORM, pid) is not None:
            db.add(ErrorPointORM(id=_gen("erp"), error_id=err.id, point_id=pid, confidence=1.0))

    db.commit()

    # 触发式 mastery 重算（PRD 12.3.4）：只有「有错因」的才重算
    # （gather_inputs 侧还有一层同样的过滤，这里是省掉无意义的计算）
    if has_cause:
        from .mastery import recompute_and_store
        for pid in payload.point_ids or []:
            recompute_and_store(db, _user.user_id, pid)
        db.commit()

    # 异步 embedding + 候选知识点匹配（v2.1-B6；embed off 时任务为空操作）
    background_tasks.add_task(_async_embed_error, err.id)

    return ErrorRecord.model_validate(_to_item(err, db))


def _async_embed_error(error_id: str) -> None:
    """后台任务：对错题原文做 embedding 并写 kb_embeddings 引用 + 向量索引。

    **强制本地模型**（source=EMBED_SRC_USER）——错题原文永不出域（PRD 12.6）。
    本地模型不可用即静默降级（宁缺毋滥、不造数，D34）：录入已成功，匹配走
    name_fuzzy，不阻断。绝不用 KB_EMBED_MODE=api 把错题原文发出去。
    """
    from database import SessionLocal
    from embedding_service import (
        EMBED_SRC_USER,
        embed_mode_for,
        embed_text,
        user_content_api_opt_in,
    )
    from models.knowledge import EmbeddingRef as EmbedRef

    db = SessionLocal()
    try:
        row = db.get(ErrorRecordORM, error_id)
        if row is None:
            return
        # D41：只有该用户在设置里显式 opt-in，用户内容才可能跟随 KB_EMBED_MODE=api 出域；
        # 默认（含无 settings 行）恒为 local。**本地失败也不会改走 api**（宁缺毋滥，D34）。
        opt_in = user_content_api_opt_in(db, row.user_id)
        mode = embed_mode_for(EMBED_SRC_USER, user_api_opt_in=opt_in)
        if mode == "off":
            return
        vec = embed_text(row.raw_text, source=EMBED_SRC_USER, user_api_opt_in=opt_in)
        if vec is None:
            return
        ref_id = _gen("ve")
        db.add(EmbedRef(
            vector_id=ref_id, ref_type="error", ref_id=error_id,
            model=mode, dim=len(vec),
        ))
        row.vector_id = ref_id
        db.commit()
        # 向量本体入本地 FAISS 索引（引用表不含向量，落盘才能检索）。
        # 🔴 必须写用户独立命名空间（store="user"）：错题原文属用户内容，
        # 写进 KB 共享索引会污染生产检索（2026-10-06 开关冲突案 · 方案 B 物理隔离）。
        from vector_store import STORE_USER
        from vector_store import add as vector_add

        vector_add(vec, ref_id, "error", error_id, mode, len(vec), store=STORE_USER)
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
    _validate_dimensions(payload.error_cause, payload.intent)

    if payload.error_type is not None:
        row.error_type = payload.error_type
    if payload.error_note is not None:
        row.error_note = payload.error_note
    # D48 两维度：契约里 errorCause/intent 不支持传 null 清除（只有 sourceExamId 支持），
    # 故这里仅在「传了非空值」时更新。
    if payload.error_cause is not None:
        row.error_cause = payload.error_cause
    if payload.intent is not None:
        row.intent = payload.intent
    if "source_exam_id" in payload.model_fields_set:
        row.source_exam_id = payload.source_exam_id  # 显式 null = 清除关联
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

    # 只有「有错因」的才喂 mastery（D48）：无错因的 star 题不触发重算
    if row.error_cause is not None:
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

    # 触发式 mastery 重算（复习改变 recall/recency 因子）。
    # star 题（无错因）也走艾宾浩斯队列，但不喂 mastery（D48）。
    if row.error_cause is not None:
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

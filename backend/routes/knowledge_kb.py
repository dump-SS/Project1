"""板块二知识库只读 API（PRD 12.3.1，契约 v1.5 学科知识库 5 条）。

- GET /knowledge/subjects                     已启用学科列表
- GET /knowledge/subjects/{code}/points       学科知识点树（扁平列表，parentId 构树）
- GET /knowledge/points/match                 文本 → Top-K（先声明，避免被 {point_id} 捕获）
- GET /knowledge/points/{pointId}             单点详情（含关联关系）
- GET /knowledge/subjects/{code}/graph        图谱（v2.1 返回树形占位）

全部需 current_user 鉴权；只读，不写库；匹配仅本地计算，不调云端 LLM。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from embedding_service import embed_text, embed_mode
from mastery_engine import compute_mastery, gather_inputs
from models.knowledge import (
    KnowledgePoint as KnowledgePointORM,
    KnowledgePointRelation as KnowledgePointRelationORM,
    KnowledgeSubject as KnowledgeSubjectORM,
)
from schemas.knowledge_kb import (
    KnowledgeGraph,
    KnowledgePoint,
    KnowledgePointDetail,
    KnowledgePointList,
    KnowledgePointMatch,
    KnowledgePointMatchList,
    KnowledgePointRelation,
    KnowledgeSubject,
    KnowledgeSubjectList,
)
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["学科知识库"])


def _point_to_item(p: KnowledgePointORM) -> dict:
    return {
        "pointId": p.id,
        "subjectCode": p.subject_code,
        "code": p.code,
        "name": p.name,
        "definition": p.definition,
        "parentId": p.parent_id,
        "difficulty": p.difficulty,
        "examWeight": p.exam_weight,
        "errorTip": p.error_tip,
    }


def _rel_to_item(r: KnowledgePointRelationORM) -> dict:
    return {
        "srcPointId": r.src_id,
        "dstPointId": r.dst_id,
        "type": r.type,
        "weight": r.weight,
    }


@router.get("/subjects", response_model=KnowledgeSubjectList, summary="已启用学科列表")
def list_subjects(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> KnowledgeSubjectList:
    rows = db.execute(
        select(KnowledgeSubjectORM).where(KnowledgeSubjectORM.enabled.is_(True))
    ).scalars().all()
    items = []
    for s in rows:
        count = db.execute(
            select(func.count())
            .select_from(KnowledgePointORM)
            .where(
                KnowledgePointORM.subject_code == s.code,
                KnowledgePointORM.enabled.is_(True),
            )
        ).scalar_one()
        items.append(
            KnowledgeSubject.model_validate(
                {
                    "subjectCode": s.code,
                    "name": s.name,
                    "gradeBand": s.grade_band,
                    "pointCount": count,
                    "version": s.version,
                }
            )
        )
    return KnowledgeSubjectList(items=items)


@router.get(
    "/subjects/{subject_code}/points",
    response_model=KnowledgePointList,
    summary="学科知识点树",
)
def list_points(
    subject_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> KnowledgePointList:
    subj = db.execute(
        select(KnowledgeSubjectORM).where(
            KnowledgeSubjectORM.code == subject_code,
            KnowledgeSubjectORM.enabled.is_(True),
        )
    ).scalars().first()
    if subj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "学科不存在或未启用"},
        )
    rows = db.execute(
        select(KnowledgePointORM)
        .where(
            KnowledgePointORM.subject_code == subject_code,
            KnowledgePointORM.enabled.is_(True),
        )
        .order_by(KnowledgePointORM.difficulty.asc(), KnowledgePointORM.code.asc())
    ).scalars().all()
    return KnowledgePointList(
        items=[KnowledgePoint.model_validate(_point_to_item(p)) for p in rows]
    )


@router.get(
    "/points/match",
    response_model=KnowledgePointMatchList,
    summary="文本 → 候选知识点 Top-K",
)
def match_points(
    text: str = Query(..., max_length=4000),
    subject: str | None = None,
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> KnowledgePointMatchList:
    """本地匹配：优先 embedding，失败/off 走 name_fuzzy 关键词。不调云端。"""
    if not text or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "text 不能为空", "field": "text"},
        )

    mode = embed_mode()
    if mode == "local":
        vec = embed_text(text)
        if vec is not None:
            from vector_store import search

            hits = search(vec, top_k=limit, subject=subject)
            if hits:
                items = []
                for ref_id, sim in hits:
                    p = db.get(KnowledgePointORM, ref_id)
                    if p is not None:
                        items.append(
                            KnowledgePointMatch.model_validate(
                                {
                                    "pointId": p.id,
                                    "name": p.name,
                                    "subjectCode": p.subject_code,
                                    "confidence": round(float(sim), 4),
                                    "matchedBy": "embedding",
                                }
                            )
                        )
                if items:
                    return KnowledgePointMatchList(items=items, matchedBy="embedding")

    # 降级：name_fuzzy（名称/别名关键词包含匹配）
    q = select(KnowledgePointORM).where(KnowledgePointORM.enabled.is_(True))
    if subject:
        q = q.where(KnowledgePointORM.subject_code == subject)
    rows = db.execute(q).scalars().all()

    tokens = [t for t in text.split() if len(t) >= 2] or list(text)
    scored: list[tuple[float, KnowledgePointORM]] = []
    for p in rows:
        hay = f"{p.code} {p.name} {p.definition or ''}"
        score = sum(1 for t in tokens if t in hay)
        if score > 0:
            scored.append((float(score) / max(len(tokens), 1), p))
    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]
    if not top:
        top = [(0.0, p) for p in rows[:limit]]
    return KnowledgePointMatchList(
        items=[
            KnowledgePointMatch.model_validate(
                {
                    "pointId": p.id,
                    "name": p.name,
                    "subjectCode": p.subject_code,
                    "confidence": round(conf, 4),
                    "matchedBy": "keyword_fallback",
                }
            )
            for conf, p in top
        ],
        matchedBy="keyword_fallback",
    )


@router.get(
    "/points/{point_id}",
    response_model=KnowledgePointDetail,
    summary="单点详情（定义/易错点/关联关系）",
)
def get_point(
    point_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> KnowledgePointDetail:
    p = db.get(KnowledgePointORM, point_id)
    if p is None or not p.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "知识点不存在"},
        )
    rels = db.execute(
        select(KnowledgePointRelationORM).where(
            (KnowledgePointRelationORM.src_id == point_id)
            | (KnowledgePointRelationORM.dst_id == point_id)
        )
    ).scalars().all()
    data = _point_to_item(p)
    data["relations"] = [_rel_to_item(r) for r in rels]
    return KnowledgePointDetail.model_validate(data)


@router.get(
    "/subjects/{subject_code}/graph",
    response_model=KnowledgeGraph,
    summary="学科概念关联图谱（含薄弱路径高亮）",
)
def get_graph(
    subject_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> KnowledgeGraph:
    rows = db.execute(
        select(KnowledgePointORM)
        .where(
            KnowledgePointORM.subject_code == subject_code,
            KnowledgePointORM.enabled.is_(True),
        )
    ).scalars().all()
    rels = db.execute(
        select(KnowledgePointRelationORM).where(
            KnowledgePointRelationORM.src_id.in_([p.id for p in rows])
        )
    ).scalars().all()

    # 薄弱路径高亮（v2.3 增量）：mastery<0.4 且样本充足的知识点 id
    weak_ids: list[str] = []
    for p in rows:
        inputs = gather_inputs(db, _user.user_id, p.id)
        result = compute_mastery(p.id, inputs)
        if result.data_sufficient and result.mastery is not None and result.mastery < 0.4:
            weak_ids.append(p.id)

    return KnowledgeGraph.model_validate(
        {
            "subjectCode": subject_code,
            "nodes": [_point_to_item(p) for p in rows],
            "edges": [_rel_to_item(r) for r in rels],
            "weakPointIds": weak_ids,
        }
    )

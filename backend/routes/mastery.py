"""板块二知识点掌握 API（PRD 12.3.4，契约 v1.5 掌握画像 3 条）。

- GET /mastery/points/{pointId}           单点 mastery + 置信度 + 样本量
- GET /mastery/subjects/{code}            学科聚合 + 子项贡献
- GET /mastery/subjects/{code}/timeline   时间序列（v2.2）

mastery 由 mastery_engine 规则计算（公式固定、权重入库）；样本 <3 不返数值。
学科聚合权重 = 知识点 exam_weight 占比。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from mastery_engine import MasteryInputs, compute_mastery, gather_inputs
from models.knowledge import (
    ErrorPoint as ErrorPointORM,
    ErrorRecord as ErrorRecordORM,
    KnowledgePoint as KnowledgePointORM,
    KnowledgeSubject as KnowledgeSubjectORM,
    PointMastery as PointMasteryORM,
    ReviewLog as ReviewLogORM,
)
from schemas.knowledge_kb import KnowledgePoint
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/mastery", tags=["知识点掌握"])


def _gather_inputs(db: Session, user_id: str, point_id: str) -> MasteryInputs:
    """向后兼容薄包装：实际逻辑迁至 mastery_engine.gather_inputs 供多路由复用。"""
    return gather_inputs(db, user_id, point_id)


def recompute_and_store(db: Session, user_id: str, point_id: str) -> PointMasteryORM:
    """重算单点 mastery 并落 kb_point_mastery（触发式：错题保存/复习提交后调用）。"""
    inputs = _gather_inputs(db, user_id, point_id)
    result = compute_mastery(point_id, inputs)

    row = db.get(PointMasteryORM, (user_id, point_id))
    if row is None:
        row = PointMasteryORM(user_id=user_id, point_id=point_id)
        db.add(row)
    row.sample_size = result.sample_size
    if result.mastery is not None:
        row.mastery = result.mastery
    return row


@router.get(
    "/points/{point_id}",
    response_model=dict,
    summary="单点掌握度 + 置信度 + 样本量",
)
def get_point_mastery(
    point_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> dict:
    p = db.get(KnowledgePointORM, point_id)
    if p is None or not p.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "知识点不存在"},
        )
    inputs = _gather_inputs(db, _user.user_id, point_id)
    result = compute_mastery(point_id, inputs)
    return {
        "pointId": point_id,
        "mastery": result.mastery,
        "dataSufficient": result.data_sufficient,
        "sampleSize": result.sample_size,
        "factors": result.factors,
        "updatedAt": datetime.utcnow().isoformat(),
    }


@router.get(
    "/subjects/{subject_code}",
    response_model=dict,
    summary="学科聚合掌握度 + 子项贡献",
)
def get_subject_mastery(
    subject_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> dict:
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
    points = db.execute(
        select(KnowledgePointORM).where(
            KnowledgePointORM.subject_code == subject_code,
            KnowledgePointORM.enabled.is_(True),
        )
    ).scalars().all()

    items = []
    weighted_sum = 0.0
    weight_total = 0.0
    samples = 0
    for p in points:
        inputs = _gather_inputs(db, _user.user_id, p.id)
        result = compute_mastery(p.id, inputs)
        item = {
            "pointId": p.id,
            "mastery": result.mastery,
            "dataSufficient": result.data_sufficient,
            "sampleSize": result.sample_size,
            "examWeight": p.exam_weight,
        }
        items.append(item)
        samples += result.sample_size
        if result.mastery is not None:
            weighted_sum += result.mastery * p.exam_weight
            weight_total += p.exam_weight

    data_sufficient = samples >= 3
    mastery = round(weighted_sum / weight_total, 4) if weight_total > 0 else None
    return {
        "subjectCode": subject_code,
        "mastery": mastery if data_sufficient else None,
        "dataSufficient": data_sufficient,
        "sampleSize": samples,
        "points": items,
    }


@router.get(
    "/subjects/{subject_code}/timeline",
    response_model=dict,
    summary="掌握度时间序列（v2.2）",
)
def get_mastery_timeline(
    subject_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> dict:
    """每日聚合：按 point_mastery.updated_at 归日取学科均值。无数据时返回空序列。"""
    points = db.execute(
        select(KnowledgePointORM).where(
            KnowledgePointORM.subject_code == subject_code,
            KnowledgePointORM.enabled.is_(True),
        )
    ).scalars().all()
    pids = [p.id for p in points]
    if not pids:
        return {"subjectCode": subject_code, "items": []}

    rows = db.execute(
        select(PointMasteryORM).where(
            PointMasteryORM.user_id == _user.user_id,
            PointMasteryORM.point_id.in_(pids),
        )
    ).scalars().all()
    if not rows:
        return {"subjectCode": subject_code, "items": []}

    by_date: dict[str, list[float]] = {}
    for r in rows:
        d = r.updated_at.date().isoformat()
        by_date.setdefault(d, []).append(r.mastery)

    items = [
        {"date": d, "mastery": round(sum(v) / len(v), 4), "sampleSize": len(v)}
        for d, v in sorted(by_date.items())
    ]
    return {"subjectCode": subject_code, "items": items}

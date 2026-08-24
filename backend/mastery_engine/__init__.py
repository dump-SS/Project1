"""知识点掌握画像（mastery）规则引擎 —— PRD 12.3.4 / 12.10。

与 state_engine 同风格：公式固定、权重入库、零外部依赖。
五因子：
- error_rate_factor        错题率（该点关联错题中 unresolved 占比的反向）
- accuracy_factor          练习正确率（v2.1 无客观测验，用复习 recall_correct 均值近似）
- recency_factor           复习新近度（最近一次复习距今）
- retention_factor         间隔保持（复习日志 recall 保持）
- unresolved_penalty       未解决错题扣分

置信度规则（PRD 12.3.4）：样本 <3 不返数值 → data_sufficient=False。
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_SAMPLES = 3  # 样本 <3 不下数值结论


@dataclass(frozen=True, slots=True)
class MasteryInputs:
    """单点掌握度的计算输入（从 kb_errors / kb_review_logs 聚合）。"""
    error_count: int = 0
    unresolved_count: int = 0
    review_count: int = 0
    recall_correct_count: int = 0
    days_since_last_review: float | None = None  # None 表示从未复习


@dataclass(slots=True)
class MasteryWeights:
    """内容维度权重组（α₁..α₅），v2.1 固定初始等权；v2.2 接入调权链路。"""
    w_error: float = 0.2
    w_accuracy: float = 0.2
    w_recency: float = 0.2
    w_retention: float = 0.2
    w_unresolved: float = 0.2


@dataclass(frozen=True, slots=True)
class PointMasteryResult:
    """单点 mastery 结果。样本不足时 mastery=None、data_sufficient=False。"""
    point_id: str
    mastery: float | None
    data_sufficient: bool
    sample_size: int
    factors: dict = field(default_factory=dict)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def compute_mastery(point_id: str, inputs: MasteryInputs, weights: MasteryWeights | None = None) -> PointMasteryResult:
    """五因子加权 mastery 计算。样本不足返回 None。"""
    if weights is None:
        weights = MasteryWeights()

    sample = (
        inputs.error_count
        + inputs.review_count
        + (1 if inputs.days_since_last_review is not None else 0)
    )
    if sample < MIN_SAMPLES:
        return PointMasteryResult(
            point_id=point_id,
            mastery=None,
            data_sufficient=False,
            sample_size=sample,
        )

    # 1. 错题率（unresolved 占比的反向）
    error_factor = 1.0 if inputs.error_count == 0 else (
        1.0 - (inputs.unresolved_count / inputs.error_count)
    )
    # 2. 练习正确率（用复习 recall 近似；无复习时 0.5 中性）
    accuracy_factor = (
        inputs.recall_correct_count / inputs.review_count
        if inputs.review_count else 0.5
    )
    # 3. 复习新近度：越近越高（30 天内线性衰减）
    if inputs.days_since_last_review is None:
        recency_factor = 0.5
    else:
        recency_factor = max(0.0, 1.0 - inputs.days_since_last_review / 30.0)
    # 4. 间隔保持：全对 1.0，有错按比例
    retention_factor = accuracy_factor if inputs.review_count else 0.5
    # 5. 未解决扣分
    unresolved_factor = 1.0 if inputs.unresolved_count == 0 else (
        1.0 - min(1.0, inputs.unresolved_count * 0.25)
    )

    score = _clamp(
        weights.w_error * error_factor
        + weights.w_accuracy * accuracy_factor
        + weights.w_recency * recency_factor
        + weights.w_retention * retention_factor
        + weights.w_unresolved * unresolved_factor
    )

    return PointMasteryResult(
        point_id=point_id,
        mastery=round(score, 4),
        data_sufficient=True,
        sample_size=sample,
        factors={
            "errorRate": round(error_factor, 4),
            "accuracy": round(accuracy_factor, 4),
            "recency": round(recency_factor, 4),
            "retention": round(retention_factor, 4),
            "unresolved": round(unresolved_factor, 4),
        },
    )


def gather_inputs(db: "object", user_id: str, point_id: str) -> MasteryInputs:
    """从 db 聚合单点 mastery 计算输入（错题数/未解决数/复习数/新近度）。

    抽出为公共函数供 knowledge_kb（图谱薄弱路径）与 plan（短板提示）复用，
    避免在多个 route 里各自实现导致口径漂移。db 为 SQLAlchemy Session。
    """
    from sqlalchemy import select

    from models.knowledge import (
        ErrorPoint as ErrorPointORM,
        ErrorRecord as ErrorRecordORM,
        ReviewLog as ReviewLogORM,
    )

    err_ids = [
        r[0]
        for r in db.execute(
            select(ErrorPointORM.error_id).where(ErrorPointORM.point_id == point_id)
        ).all()
    ]
    if not err_ids:
        return MasteryInputs()

    errors = db.execute(
        select(ErrorRecordORM).where(
            ErrorRecordORM.id.in_(err_ids),
            ErrorRecordORM.user_id == user_id,
            ErrorRecordORM.deleted_at.is_(None),
        )
    ).scalars().all()
    unresolved = sum(1 for e in errors if e.status == "open")

    logs = db.execute(
        select(ReviewLogORM)
        .where(ReviewLogORM.error_id.in_(err_ids))
        .order_by(ReviewLogORM.reviewed_at.desc())
    ).scalars().all()
    recall_ok = sum(1 for lg in logs if lg.recall_correct)

    days_since = None
    if logs:
        from datetime import datetime

        latest = logs[0].reviewed_at
        if latest.tzinfo is not None:
            latest = latest.replace(tzinfo=None)
        days_since = (datetime.utcnow() - latest).total_seconds() / 86400.0

    return MasteryInputs(
        error_count=len(errors),
        unresolved_count=unresolved,
        review_count=len(logs),
        recall_correct_count=recall_ok,
        days_since_last_review=days_since,
    )


def compute_weakness_hints(
    db: "object",
    user_id: str,
    subject_codes: list[str] | None,
    threshold: float = 0.7,
    limit: int = 3,
) -> list[dict]:
    """计算短板提示（v2.3 Plan.weaknessHints）。

    遍历用户在给定学科下的知识点，计算 mastery，筛选 mastery<threshold 且样本充足者，
    按 mastery 升序取 Top-N。返回 dict 列表，与 PlanWeaknessHint schema 对齐。
    subject_codes 为空或无匹配知识点时返回空列表。
    """
    from sqlalchemy import select

    from models.knowledge import (
        KnowledgePoint as KnowledgePointORM,
        KnowledgeSubject as KnowledgeSubjectORM,
    )

    q = select(KnowledgePointORM).where(KnowledgePointORM.enabled.is_(True))
    if subject_codes:
        q = q.where(KnowledgePointORM.subject_code.in_(subject_codes))
    points = db.execute(q).scalars().all()

    candidates: list[tuple[float, KnowledgePointORM]] = []
    for p in points:
        inputs = gather_inputs(db, user_id, p.id)
        result = compute_mastery(p.id, inputs)
        if result.data_sufficient and result.mastery is not None and result.mastery < threshold:
            candidates.append((result.mastery, p))

    candidates.sort(key=lambda x: x[0])
    return [
        {
            "pointId": p.id,
            "pointName": p.name,
            "mastery": m,
            "subjectCode": p.subject_code,
        }
        for m, p in candidates[:limit]
    ]

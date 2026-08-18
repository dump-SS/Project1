"""/me/weight-config 系列。

PRD 5.2 第 4 点 / 6.5：AI 调权的查询接口。
- GET /me/weight-config：当前权重 + 最近调权日志（5 条）
- POST /me/weight-config/tune-now：手动触发一次调权（不走后台）
- GET /me/state-breakdown：调权后算法计算结果（按调权后权重算出"行为子分 × α + 自评子分 × β"
  的最终窗口分，附各子分均值，让用户看到调权对状态分的影响）
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.learning_record import LearningRecord as LearningRecordORM
from models.weight import UserWeightConfig, WeightAdjustLog
from schemas.user import User
from state_calculator import compute_window_for_records, orm_record_to_engine_input
from weight_tuning import _get_or_create_weight_config, tune_user_weights
from .deps import current_user

router = APIRouter(prefix="/me", tags=["AI 调权"])


class WeightSnapshot(BaseModel):
    """某次调权前后的权重快照（PRD 5.2 调权留痕）。"""

    model_config = ConfigDict(populate_by_name=True)

    alpha: float
    beta: float
    w1: float
    w2: float
    w3: float
    w4: float
    w5: float
    w6: float


class WeightAdjustLogItem(BaseModel):
    """单条调权日志（PRD 6.5 可解释性）。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    before: WeightSnapshot
    after: WeightSnapshot
    reason: str
    reverted: bool
    revert_reason: str | None = Field(None, alias="revertReason")
    effective_at: datetime = Field(..., alias="effectiveAt")


class WeightConfigResponse(BaseModel):
    """当前权重 + 最近 5 条调权日志。"""

    model_config = ConfigDict(populate_by_name=True)

    current: WeightSnapshot
    updated_at: datetime = Field(..., alias="updatedAt")
    recent_logs: List[WeightAdjustLogItem] = Field(..., alias="recentLogs")


def _snapshot(row: UserWeightConfig) -> dict:
    return {
        "alpha": row.alpha,
        "beta": row.beta,
        "w1": row.w1,
        "w2": row.w2,
        "w3": row.w3,
        "w4": row.w4,
        "w5": row.w5,
        "w6": row.w6,
    }


def _log_to_dict(log: WeightAdjustLog) -> dict:
    return {
        "id": log.id,
        "before": {
            "alpha": log.before_alpha, "beta": log.before_beta,
            "w1": log.before_w1, "w2": log.before_w2, "w3": log.before_w3,
            "w4": log.before_w4, "w5": log.before_w5, "w6": log.before_w6,
        },
        "after": {
            "alpha": log.after_alpha, "beta": log.after_beta,
            "w1": log.after_w1, "w2": log.after_w2, "w3": log.after_w3,
            "w4": log.after_w4, "w5": log.after_w5, "w6": log.after_w6,
        },
        "reason": log.reason,
        "reverted": log.reverted,
        "revertReason": log.revert_reason,
        "effectiveAt": log.effective_at,
    }


@router.get(
    "/weight-config",
    response_model=WeightConfigResponse,
    summary="读取当前权重 + 最近调权日志",
)
def get_weight_config(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> WeightConfigResponse:
    cfg = _get_or_create_weight_config(db, _user.user_id)
    logs = db.execute(
        select(WeightAdjustLog)
        .where(WeightAdjustLog.user_id == _user.user_id)
        .order_by(WeightAdjustLog.effective_at.desc())
        .limit(5)
    ).scalars().all()
    return WeightConfigResponse.model_validate({
        "current": _snapshot(cfg),
        "updatedAt": cfg.updated_at,
        "recentLogs": [_log_to_dict(l) for l in logs],
    })


class TuneNowResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    tuned: bool
    message: str


@router.post(
    "/weight-config/tune-now",
    response_model=TuneNowResponse,
    summary="手动触发一次调权（演示用）",
)
def post_tune_now(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> TuneNowResponse:
    """手动触发调权，绕过 _should_tune 的周期/阈值限制（演示入口）。

    真实流程是每条学习记录后由 background_tasks 异步触发。
    """
    # 调权前先清空"上次调权时间"的抑制效果：临时把 effective_at 改到 8 天前
    # 让 _should_tune 误以为距离上次已过 7 天，从而通过周期检查；
    # 用户仍然受记录数阈值约束（设置里 aiWeightTuningEnabled 也需为 True）
    last_log = db.execute(
        select(WeightAdjustLog)
        .where(
            WeightAdjustLog.user_id == _user.user_id,
            WeightAdjustLog.reverted.is_(False),
        )
        .order_by(WeightAdjustLog.effective_at.desc())
        .limit(1)
    ).scalars().first()
    if last_log is not None:
        last_log.effective_at = datetime.utcnow() - __import__("datetime").timedelta(days=8)
        db.commit()

    tuned = tune_user_weights(db, _user.user_id)
    return TuneNowResponse.model_validate({
        "tuned": tuned,
        "message": "调权成功，权重已更新" if tuned else "未达到调权条件或 LLM 建议越界，已回退",
    })


# ---------- 调权后算法计算结果（个人数据页 ⑧ 模块用） ----------

class StateBreakdownResponse(BaseModel):
    """按当前权重计算的窗口分 + 各子分贡献 + 占比 + 标签/趋势。

    让用户看到"调权改了 α/β → 状态分怎么变"。
    """
    model_config = ConfigDict(populate_by_name=True)

    subject: str
    window_score: float | None = Field(..., alias="windowScore")
    behavior_sub_avg: float = Field(..., alias="behaviorSubAvg")
    self_report_sub_avg: float = Field(..., alias="selfReportSubAvg")
    behavior_contribution: float = Field(..., alias="behaviorContribution")
    self_report_contribution: float = Field(..., alias="selfReportContribution")
    behavior_share: float = Field(..., alias="behaviorShare")
    self_report_share: float = Field(..., alias="selfReportShare")
    record_count: int = Field(..., alias="recordCount")
    state_label: str | None = Field(None, alias="stateLabel")
    trend: str | None = None
    signals: List[str] = []
    # 当前权重（让前端能直接显示 α/β/w1-w6）
    weights: dict
    # 窗口大小（PRD：7 天）
    window_size: int = Field(7, alias="windowSize")


def _fetch_window_records(
    db: Session, user_id: str, limit: int = 7
) -> list[LearningRecordORM]:
    """最近 limit 条记录，时间正序。同 assessment.py 的 _window_rows 排序规则。"""
    rows = db.execute(
        select(LearningRecordORM)
        .where(LearningRecordORM.user_id == user_id)
        .order_by(
            LearningRecordORM.started_at.desc(),
            LearningRecordORM.created_at.desc(),
            LearningRecordORM.id.desc(),
        )
        .limit(limit)
    ).scalars().all()
    return list(reversed(rows))


@router.get(
    "/state-breakdown",
    response_model=StateBreakdownResponse,
    summary="按当前权重计算的窗口分 + 子分贡献分解（调权后算法结果）",
)
def get_state_breakdown(
    subject: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> StateBreakdownResponse:
    """按用户当前权重（来自 UserWeightConfig，AI 调权后）计算窗口分 + 子分贡献。

    与 /assessments/current 互补：后者给"状态标签/趋势/displayText"，
    本接口给"调权改了 α/β 后，状态分究竟由行为/自评各贡献了多少"。
    """
    cfg = _get_or_create_weight_config(db, _user.user_id)
    weights_dict = _snapshot(cfg)

    # 构造引擎 WeightConfig
    from state_engine.types import WeightConfig as _WC
    weights = _WC(
        alpha=cfg.alpha, beta=cfg.beta,
        w1=cfg.w1, w2=cfg.w2, w3=cfg.w3,
        w4=cfg.w4, w5=cfg.w5, w6=cfg.w6,
    )

    # 默认取有记录的主学科（与 assessment.py /current 一致），允许 query 覆盖
    if subject is None:
        result = db.execute(
            select(LearningRecordORM.subject)
            .where(LearningRecordORM.user_id == _user.user_id)
            .distinct()
        ).scalars().all()
        subject = sorted(set(result))[0] if result else "math"

    rows = _fetch_window_records(db, _user.user_id, limit=7)
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]
    from state_engine.adapter import compute_subscore_breakdown, compute_window_for_records
    breakdown = compute_subscore_breakdown(engine_inputs, weights=weights)
    if breakdown is None:
        # 数据为空：返回空状态（窗口 0）
        return StateBreakdownResponse.model_validate({
            "subject": subject,
            "windowScore": None,
            "behaviorSubAvg": 0.0,
            "selfReportSubAvg": 0.0,
            "behaviorContribution": 0.0,
            "selfReportContribution": 0.0,
            "behaviorShare": 0.5,
            "selfReportShare": 0.5,
            "recordCount": 0,
            "stateLabel": "insufficient_data",
            "trend": None,
            "signals": [],
            "weights": weights_dict,
            "windowSize": 7,
        })

    # 同时计算标签/趋势（用同一批记录与权重）
    window = compute_window_for_records(engine_inputs, weights=weights)

    return StateBreakdownResponse.model_validate({
        "subject": subject,
        "windowScore": breakdown["windowScore"],
        "behaviorSubAvg": breakdown["behaviorSubAvg"],
        "selfReportSubAvg": breakdown["selfReportSubAvg"],
        "behaviorContribution": breakdown["behaviorContribution"],
        "selfReportContribution": breakdown["selfReportContribution"],
        "behaviorShare": breakdown["behaviorShare"],
        "selfReportShare": breakdown["selfReportShare"],
        "recordCount": breakdown["recordCount"],
        "stateLabel": window.state_label.value if window.data_sufficient else "insufficient_data",
        "trend": window.trend.value if window.trend else None,
        "signals": window.signals,
        "weights": weights_dict,
        "windowSize": 7,
    })

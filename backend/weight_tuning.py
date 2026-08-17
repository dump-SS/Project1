"""AI 调权服务（PRD 5.2 第 4 点）。

按周期（每周一次或累计 N 条新记录）离线批量执行：
1. 读用户当前权重（UserWeightConfig，无则建默认值）
2. 组装该用户近期结构化特征序列，发给 LLM 请求调权建议
3. 用 state_engine.weights.validate_adjustment 强制校验（α/β ∈ [0.3,0.7]、子项 ∈ [0.1,0.5]、单次变动 ≤0.1）
4. 通过 → 更新 UserWeightConfig；失败 → 回退到当前权重（不是初始值）
5. 每次调权/回退都写 WeightAdjustLog 留痕，支持回溯与人工回滚
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from llm_provider import get_provider
from models.learning_record import LearningRecord
from models.user import Settings as SettingsModel
from models.weight import UserWeightConfig, WeightAdjustLog
from state_engine.adapter import orm_record_to_engine_input, compute_window_for_records
from state_engine.types import WeightConfig
from state_engine.weights import WeightAdjustment, validate_adjustment

logger = logging.getLogger(__name__)

# 触发调权的条件：累计新记录数达到阈值（PRD 5.2：不在单次学习后实时调权）
TUNE_THRESHOLD_RECORDS = 10


def _get_or_create_weight_config(db: Session, user_id: str) -> UserWeightConfig:
    cfg = db.get(UserWeightConfig, user_id)
    if cfg is None:
        cfg = UserWeightConfig(user_id=user_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _current_weights(cfg: UserWeightConfig) -> WeightConfig:
    return WeightConfig(
        alpha=cfg.alpha, beta=cfg.beta,
        w1=cfg.w1, w2=cfg.w2, w3=cfg.w3,
        w4=cfg.w4, w5=cfg.w5, w6=cfg.w6,
    )


def _should_tune(db: Session, user_id: str) -> bool:
    """是否触发调权：累计新记录数 ≥ 阈值，且用户开启了 ai_weight_tuning_enabled。"""
    settings = db.get(SettingsModel, user_id)
    if settings and not settings.ai_weight_tuning_enabled:
        logger.info("[AI 调权] 用户 %s 已关闭 AI 自动调权，跳过", user_id)
        return False
    recent_count = db.execute(
        select(func.count()).select_from(LearningRecord).where(LearningRecord.user_id == user_id)
    ).scalar_one()
    return recent_count >= TUNE_THRESHOLD_RECORDS


def _build_features(db: Session, user_id: str) -> dict:
    """组装近期结构化特征（PRD 5.2：各维度标准化值、状态分、趋势、计划完成情况）。"""
    rows = db.execute(
        select(LearningRecord)
        .where(LearningRecord.user_id == user_id)
        .order_by(LearningRecord.started_at.desc())
        .limit(14)  # 最近 2 周窗口
    ).scalars().all()
    engine_inputs = [orm_record_to_engine_input(r) for r in rows]
    window = compute_window_for_records(engine_inputs) if engine_inputs else None
    return {
        "recordCount": len(rows),
        "windowScore": window.window_score if window else None,
        "trend": window.trend.value if window else None,
        "stateLabel": window.state_label.value if window else None,
        "signals": window.signals if window else [],
        # TODO: 计划完成情况（接 PlanTask 后补充）
    }


def _suggest_weights(features: dict, current: WeightConfig) -> WeightAdjustment | None:
    """向 LLM 请求调权建议（PRD 5.2：输出建议值 + 理由）。"""
    provider = get_provider()
    prompt = (
        f"基于该用户近期的学习状态特征，建议状态分公式的权重调整。\n"
        f"当前权重：alpha={current.alpha}, beta={current.beta}\n"
        f"近期特征：{json.dumps(features, ensure_ascii=False)}\n"
        f"要求：\n"
        f"1. alpha 和 beta 都在 [0.3, 0.7] 之间，且 alpha + beta = 1\n"
        f"2. 行为子项 w1/w2/w3 和自评子项 w4/w5/w6 各在 [0.1, 0.5]，同组和为 1\n"
        f"3. 任一权重与当前值变动不超过 0.1\n"
        f"4. 返回 JSON：{{alpha, beta, w1, w2, w3, w4, w5, w6, reason}}\n"
        f"5. reason 必须给出调整理由（用于可解释性留痕）"
    )
    text = provider.generate(prompt, context={"task": "weight_tuning"})
    if not text:
        return None
    try:
        data = json.loads(text)
        return WeightAdjustment(
            alpha=data["alpha"], beta=data["beta"],
            w1=data["w1"], w2=data["w2"], w3=data["w3"],
            w4=data["w4"], w5=data["w5"], w6=data["w6"],
            reason=data.get("reason", "未提供理由"),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("[AI 调权] LLM 返回格式非法: %s", e)
        return None


def tune_user_weights(db: Session, user_id: str) -> bool:
    """为用户执行一次调权（PRD 5.2 第 4 点的完整流程）。

    Returns:
        True: 权重被成功调整；False: 未调整（未触发/LLM 失败/校验回退）
    """
    if not _should_tune(db, user_id):
        return False

    cfg = _get_or_create_weight_config(db, user_id)
    current = _current_weights(cfg)

    # 组装特征 → LLM 建议
    features = _build_features(db, user_id)
    proposed = _suggest_weights(features, current)
    if proposed is None:
        logger.info("[AI 调权] 用户 %s LLM 未给出有效建议，跳过", user_id)
        return False

    # 硬限制校验（PRD 5.2：不依赖提示词约束，代码层强制）
    result = validate_adjustment(current, proposed)

    if result.valid and result.new_weights:
        # 通过：更新权重表
        new_w = result.new_weights
        cfg.alpha = new_w.alpha
        cfg.beta = new_w.beta
        cfg.w1, cfg.w2, cfg.w3 = new_w.w1, new_w.w2, new_w.w3
        cfg.w4, cfg.w5, cfg.w6 = new_w.w4, new_w.w5, new_w.w6
        cfg.updated_at = datetime.utcnow()

        # 留痕
        log = WeightAdjustLog(
            id=f"wlog_{user_id}_{int(datetime.utcnow().timestamp())}",
            user_id=user_id,
            before_alpha=current.alpha, before_beta=current.beta,
            before_w1=current.w1, before_w2=current.w2, before_w3=current.w3,
            before_w4=current.w4, before_w5=current.w5, before_w6=current.w6,
            after_alpha=new_w.alpha, after_beta=new_w.beta,
            after_w1=new_w.w1, after_w2=new_w.w2, after_w3=new_w.w3,
            after_w4=new_w.w4, after_w5=new_w.w5, after_w6=new_w.w6,
            reason=proposed.reason,
            reverted=False,
        )
        db.add(log)
        db.commit()
        logger.info("[AI 调权] 用户 %s 权重已调整: %s", user_id, proposed.reason)
        return True

    # 越界：回退到当前权重（不是初始值，PRD 5.2 明确要求）
    log = WeightAdjustLog(
        id=f"wlog_{user_id}_{int(datetime.utcnow().timestamp())}",
        user_id=user_id,
        before_alpha=current.alpha, before_beta=current.beta,
        before_w1=current.w1, before_w2=current.w2, before_w3=current.w3,
        before_w4=current.w4, before_w5=current.w5, before_w6=current.w6,
        after_alpha=current.alpha, after_beta=current.beta,
        after_w1=current.w1, after_w2=current.w2, after_w3=current.w3,
        after_w4=current.w4, after_w5=current.w5, after_w6=current.w6,
        reason=proposed.reason,
        reverted=True,
        revert_reason=result.rejection_reason,
    )
    db.add(log)
    db.commit()
    logger.warning(
        "[AI 调权] 用户 %s 模型建议越界，已回退到当前权重: %s",
        user_id, result.rejection_reason,
    )
    return False

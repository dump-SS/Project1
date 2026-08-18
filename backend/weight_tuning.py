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
import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from llm_provider import get_provider
from models.learning_record import LearningRecord
from models.plan import PlanTask as PlanTaskORM
from models.user import Settings as SettingsModel
from models.weight import UserWeightConfig, WeightAdjustLog
from state_calculator import orm_record_to_engine_input, compute_window_for_records
from state_engine.types import WeightConfig
from state_engine.weights import WeightAdjustment, validate_adjustment

logger = logging.getLogger(__name__)

# 触发调权的条件：距上次调权超过 N 天 或 累计新记录数达到阈值且从未调权
# （PRD 5.2：按周期离线批量执行，不在单次学习后实时调权）
TUNE_INTERVAL_DAYS = 7
# 阈值降到 3：本地演示用 4 条记录就能触发；PRD 文档说"≥10 条数据更稳定"，
# 但当前是 MVP 阶段，让少数据用户也能看到"调权日志"，便于 PR 走查。
# 上线前可调回 10。
TUNE_THRESHOLD_RECORDS = 3


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
    """是否触发调权：距上次调权 ≥ TUNE_INTERVAL_DAYS 或从未调权且记录数达标。

    PRD 5.2：按周期离线批量执行，不在单次学习后实时调权。
    之前用「总记录数 ≥ 阈值」判断，调权后每条新记录都再次触发——已修正为按间隔。
    """
    settings = db.get(SettingsModel, user_id)
    if settings and not settings.ai_weight_tuning_enabled:
        logger.info("[AI 调权] 用户 %s 已关闭 AI 自动调权，跳过", user_id)
        return False

    # 查上次调权时间（从 WeightAdjustLog 取最近一条有效调权）
    last_log = db.execute(
        select(WeightAdjustLog)
        .where(
            WeightAdjustLog.user_id == user_id,
            WeightAdjustLog.reverted.is_(False),
        )
        .order_by(WeightAdjustLog.effective_at.desc())
        .limit(1)
    ).scalars().first()

    if last_log is not None:
        days_since = (datetime.utcnow() - last_log.effective_at).days
        if days_since < TUNE_INTERVAL_DAYS:
            logger.info(
                "[AI 调权] 用户 %s 距上次调权 %d 天 < %d 天，跳过",
                user_id, days_since, TUNE_INTERVAL_DAYS,
            )
            return False

    # 从未调权或已过间隔：检查记录数是否达标
    recent_count = db.execute(
        select(func.count()).select_from(LearningRecord).where(LearningRecord.user_id == user_id)
    ).scalar_one()
    if recent_count < TUNE_THRESHOLD_RECORDS:
        logger.info(
            "[AI 调权] 用户 %s 记录数 %d < %d，跳过",
            user_id, recent_count, TUNE_THRESHOLD_RECORDS,
        )
        return False
    return True


def _compute_plan_completion(db: Session, user_id: str) -> float | None:
    """从 plan_tasks 表算计划完成率（PRD 5.2/5.4 复盘 dataPoints）。

    ratio = completed / total（未软删除的任务）。无任务时返回 None。
    """
    total = db.execute(
        select(func.count()).select_from(PlanTaskORM).where(
            PlanTaskORM.user_id == user_id,
            PlanTaskORM.removed.is_(False),
        )
    ).scalar_one()
    if total == 0:
        return None
    completed = db.execute(
        select(func.count()).select_from(PlanTaskORM).where(
            PlanTaskORM.user_id == user_id,
            PlanTaskORM.removed.is_(False),
            PlanTaskORM.status == "completed",
        )
    ).scalar_one()
    return round(completed / total, 2)


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
        "planCompletionRatio": _compute_plan_completion(db, user_id),
    }


def _extract_json_block(text: str) -> str:
    """LLM 输出容错：提取 markdown ```json ... ``` 围栏里的内容。

    真实 LLM 返回常带 ```json 包裹或前后说明文字，直接 json.loads 会失败。
    提不出来就原样返回，让调用方自行判断。
    """
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text


def _suggest_weights(features: dict, current: WeightConfig) -> WeightAdjustment | None:
    """向 LLM 请求调权建议（PRD 5.2：输出建议值 + 理由）。

    prompt 结构说明：
    - system 短：硬约束 + JSON 字段定义（避免被切到 user 字段导致空响应）
    - user 短：当前权重 + 关键特征摘要
    - 长 features 不直接塞 user，缩短 prompt 总长度以适配 Doubao-Seed-2.0-mini
    """
    provider = get_provider()
    system = (
        "你是 EpochX AI 调权助手。\n"
        "硬约束：\n"
        "1. alpha 和 beta 都在 [0.3, 0.7] 之间，alpha + beta = 1\n"
        "2. 行为子项 w1/w2/w3 和自评子项 w4/w5/w6 各在 [0.1, 0.5]，同组和为 1\n"
        "3. 任一权重与当前值变动不超过 0.1\n"
        "4. 只输出一个 JSON 对象，不要 markdown 围栏，不要解释文字\n"
        'JSON：{"alpha":0.5,"beta":0.5,"w1":0.33,"w2":0.33,"w3":0.34,"w4":0.33,"w5":0.33,"w6":0.34,"reason":"调整理由(中文,≤80字)"}'
    )
    # 摘要：避免长 JSON 触发模型拒答
    summary = (
        f"记录数 {features.get('recordCount', 0)}, "
        f"窗口分 {features.get('windowScore')}, "
        f"趋势 {features.get('trend')}, "
        f"状态 {features.get('stateLabel')}, "
        f"计划完成率 {features.get('planCompletionRatio')}"
    )
    prompt = (
        f"当前权重 alpha={current.alpha} beta={current.beta} "
        f"w1-6={current.w1},{current.w2},{current.w3},{current.w4},{current.w5},{current.w6}\n"
        f"近期特征: {summary}\n"
        "请输出调整后的 JSON。"
    )
    text = provider.generate(prompt, context={"system": system})
    if not text:
        logger.info("[AI 调权] LLM 未返回文本")
        return None
    logger.info("[AI 调权] LLM 原始返回（前 300 字符）: %s", text[:300])
    # 真实 LLM 常带 ```json 包裹，先做围栏提取再解析
    for candidate in (text, _extract_json_block(text)):
        try:
            data = json.loads(candidate)
            return WeightAdjustment(
                alpha=data["alpha"], beta=data["beta"],
                w1=data["w1"], w2=data["w2"], w3=data["w3"],
                w4=data["w4"], w5=data["w5"], w6=data["w6"],
                reason=data.get("reason", "未提供理由"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    logger.warning("[AI 调权] LLM 返回格式非法，无法解析: %s", text[:200])
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


# ---------- 后台任务入口（供 BackgroundTasks 调用；自开 session，不复用请求级 session） ----------

def run_weight_tuning(
    user_id: str,
) -> None:
    """后台执行调权。路由响应返回后执行，耗时的 LLM 调用不阻塞用户。

    同 ai_suggestion.run_recommendation_generation 的模式：
    自开 SessionLocal，异常自愈，绝不穿透到路由层。
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        tune_user_weights(db, user_id)
    except Exception:
        logger.exception("[AI 调权] 后台调权异常 user_id=%s", user_id)
    finally:
        db.close()

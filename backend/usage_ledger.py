"""usage_ledger 写入器（#9 / D38）——G 板块。

按用户记录模型数值成本。与 ai_call_log 同一范式：自建会话、所有写入失败一律吞掉，
绝不影响业务主流程（计量是辅助能力，PRD 8.2）。

铁律（refactor-implementation-notes §1）：
- usage_ledger **只存数值**（tokens / 成本 / 档位 / 模型名），不存任何提示词或输出内容；
- 与刻意去身份化的 AICallLog 分两套，不合并；**绝不给 AICallLog 补身份字段**。
- 写入挂 provider 出口（llm_provider.generate 成功返回后调用），因此 B 板块 Chat
  首次真实调用前本模块必须已就位（全项目唯一硬时序）。

身份来源：调用方在 provider.generate 的 context 里带 user_id / feature_tier /
reasoning_tier。context 缺 user_id 时不写行（无法归属成本），仅 debug 日志——
现有「无身份调用」留给 AICallLog 审计，两套表各司其职。
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

__all__ = ["record_usage", "FEATURE_TIERS"]

# 合法功能档位（openapi UsageFeatureTier）。chat=用户主动有感；embedded=系统自动无感；
# advanced=高级稀有调用；multimodal=文件解析。新增档位属契约变更。
FEATURE_TIERS = {"chat", "embedded", "advanced", "multimodal"}

# 内部计价表：模型名 → (输入元/1M tokens, 输出元/1M tokens)。
# pilot 不收费，cost 只是为定价留的数据口径（数值成本，非对用户计费）；
# 具体单价为**占位口径**，上线定价评估前由运营核定后补登模型行。
# 未登记模型走 FALLBACK_PRICING，保证「每次真实调用都有成本数值」可追溯。
MODEL_PRICING: dict[str, tuple[float, float]] = {}
FALLBACK_PRICING: tuple[float, float] = (2.0, 8.0)


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """按内部计价表算数值成本；未登记模型走兜底单价。"""
    price_in, price_out = MODEL_PRICING.get(model, FALLBACK_PRICING)
    return round(tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out, 6)


def record_usage(context: dict | None, model: str, tokens_in: int, tokens_out: int) -> None:
    """记录一次真实 LLM 调用的数值成本。

    在 llm_provider.generate 成功拿到响应后调用（无论 usage 字段是否齐全——
    供应商没回 usage 时记 0，行仍在，调用本身可追溯）。
    MockProvider 不产生真实成本，不调用本函数。
    """
    ctx = context or {}
    user_id = ctx.get("user_id")
    if not user_id:
        logger.debug("[usage_ledger] context 无 user_id，不记录（成本无法归属）")
        return

    feature_tier = ctx.get("feature_tier") or "embedded"
    if feature_tier not in FEATURE_TIERS:
        logger.warning("[usage_ledger] 非法 feature_tier=%r，按 embedded 记", feature_tier)
        feature_tier = "embedded"
    reasoning_tier = ctx.get("reasoning_tier")  # quick/standard/deep 或 None

    try:
        from database import SessionLocal
        from models.governance import UsageLedger

        db = SessionLocal()
        try:
            db.add(UsageLedger(
                id=f"ul_{uuid.uuid4().hex[:12]}",
                user_id=user_id,
                feature_tier=feature_tier,
                reasoning_tier=reasoning_tier,
                model=model or "unknown",
                tokens_in=int(tokens_in or 0),
                tokens_out=int(tokens_out or 0),
                cost=compute_cost(model or "", int(tokens_in or 0), int(tokens_out or 0)),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — 计量失败绝不阻断业务
        logger.debug("[usage_ledger] 写入失败（已忽略）: %s", e)

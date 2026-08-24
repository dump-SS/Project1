"""AICallLog 写入器（PRD 6.5 / 6.4）。

集中记录 LLM 调用与出域拦截，供成本监控与问题回溯。所有写入失败一律吞掉，
绝不影响业务主流程（PRD 8.2：核心流程必须可用；留痕是辅助能力）。

铁律：本模块不接受也不存储任何用户身份字段（PRD §7）。
"""
from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)

__all__ = ["log_call", "log_egress_block"]


def _persist(
    function_type: str,
    data_class: str | None,
    input_digest: str | None,
    latency_ms: int | None,
    success: bool,
    egress_blocked: bool = False,
    cost_units: float | None = None,
    error_msg: str | None = None,
) -> None:
    try:
        from database import SessionLocal
        from models.ai_call_log import AICallLog

        db = SessionLocal()
        try:
            db.add(AICallLog(
                id=f"acl_{uuid.uuid4().hex[:12]}",
                function_type=function_type,
                data_class=data_class,
                input_digest=(input_digest[:256] if input_digest else None),
                latency_ms=latency_ms,
                success=success,
                egress_blocked=egress_blocked,
                cost_units=cost_units,
                error_msg=(error_msg[:256] if error_msg else None),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — 留痕失败绝不阻断业务
        logger.debug("[AICallLog] 写入失败（已忽略）: %s", e)


def log_call(
    context: dict | None,
    latency_ms: int | None,
    success: bool,
    error_msg: str | None = None,
) -> None:
    """记录一次 LLM 调用结果。context 来自 provider.generate(context=...)。"""
    ctx = context or {}
    _persist(
        function_type=ctx.get("scene") or "unknown",
        data_class=ctx.get("data_class"),
        input_digest=ctx.get("input_digest"),
        latency_ms=latency_ms,
        success=success,
        egress_blocked=False,
        error_msg=error_msg,
    )


def log_egress_block(context: dict | None, reason: str) -> None:
    """记录一次出域拦截（knowledge_raw 越权或聚合白名单外字段）。"""
    ctx = context or {}
    _persist(
        function_type=ctx.get("scene") or "unknown",
        data_class=ctx.get("data_class"),
        input_digest=ctx.get("input_digest"),
        latency_ms=0,
        success=False,
        egress_blocked=True,
        error_msg=reason,
    )


def _make_input_digest(context: dict | None) -> str | None:
    """从 context 生成出域 payload 摘要（仅字段名清单，不含值）。"""
    fields = (context or {}).get("egress_fields")
    if not isinstance(fields, dict):
        return None
    return ",".join(sorted(fields.keys())) if fields else None

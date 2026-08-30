"""板块三聚合预计算 job（M3，决策 v1.7 §4.2/§4.9/§4.5）。

对当前周期每个 metric × stage 组合：
- pool_size < k → 删除该组合存量聚合行（重算语义：不落新行不够，必须删旧行）
- pool_size ≥ k → 计算分位数+直方图（含桶合并 n=3）并 upsert 物化表
每日低峰运行；撤回/授权变更后延迟批量重算即此 job（延迟 ≤ 24h）。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import delete, select

from community_aggregate import aggregate
from config import settings
from database import SessionLocal
from models.community import CommunityAggregate, CommunityFeature

logger = logging.getLogger(__name__)


def _current_iso_week() -> str:
    from datetime import date

    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run_community_aggregation() -> dict:
    """后台入口：自开 session，重算当前周期全部 metric×stage 组合。"""
    db = SessionLocal()
    try:
        return aggregate_all(db)
    except Exception:  # noqa: BLE001
        logger.exception("[COMMUNITY] 聚合失败")
        return {"combinations": 0, "written": 0}
    finally:
        db.close()


def aggregate_all(db) -> dict:
    period = _current_iso_week()
    written = 0
    combos = set(
        (row.stage, row.metric)
        for row in db.execute(
            select(CommunityFeature.stage, CommunityFeature.metric).where(
                CommunityFeature.period == period
            )
        ).all()
    )
    k = settings.community_min_pool

    # 全量维度组合（metric × stage），含 pool 为空的组合（需删除旧行）
    for stage in ("junior", "senior"):
        for metric in ("hours", "focus", "fatigue", "completion"):
            values = [
                row.value
                for row in db.execute(
                    select(CommunityFeature.value).where(
                        CommunityFeature.period == period,
                        CommunityFeature.stage == stage,
                        CommunityFeature.metric == metric,
                    )
                ).scalars().all()
            ]
            existing = db.execute(
                select(CommunityAggregate).where(
                    CommunityAggregate.period == period,
                    CommunityAggregate.stage == stage,
                    CommunityAggregate.metric == metric,
                )
            ).scalars().first()

            if len(values) < k:
                # 第二重/第一重校验：不足 k，删除存量聚合行
                if existing is not None:
                    db.delete(existing)
                continue

            result = aggregate(values, metric)
            if existing is None:
                existing = CommunityAggregate(
                    id=f"cagg_{uuid.uuid4().hex[:12]}",
                    period=period, stage=stage, metric=metric,
                    pool_size=len(values),
                    percentiles=json.dumps({
                        "p25": result["p25"], "p50": result["p50"], "p75": result["p75"],
                    }),
                    histogram=json.dumps(result["histogram"]),
                )
                db.add(existing)
            else:
                existing.pool_size = len(values)
                existing.percentiles = json.dumps({
                    "p25": result["p25"], "p50": result["p50"], "p75": result["p75"],
                })
                existing.histogram = json.dumps(result["histogram"])
                existing.computed_at = datetime.utcnow()
            written += 1

    db.commit()
    logger.info("[COMMUNITY] 聚合完成 pool组合=%d 写入=%d", len(combos), written)
    return {"combinations": len(combos), "written": written}


def start_community_scheduler():
    """周日 23:59 统一抽取 + 聚合重算（§4.7 已拍板时点）。返回 asyncio task。"""
    import asyncio

    from jobs.community_extraction import run_community_extraction

    async def _loop():
        while True:
            try:
                now = datetime.now()
                # 下一个周日 23:59（ISO 周末为周日 23:59）
                days_ahead = (6 - now.weekday()) % 7  # weekday(): 周一=0 … 周日=6
                next_run = (now + __import__("datetime").timedelta(days=days_ahead)).replace(
                    hour=23, minute=59, second=0, microsecond=0
                )
                if next_run <= now:
                    next_run += __import__("datetime").timedelta(days=7)
                await asyncio.sleep((next_run - now).total_seconds())
                run_community_extraction()
                run_community_aggregation()
            except Exception:  # noqa: BLE001
                logger.exception("[COMMUNITY] 定时任务异常")

    import logging as _logging
    _logging.getLogger(__name__).info("[COMMUNITY] 调度器已启动（每周日 23:59）")
    return asyncio.create_task(_loop())

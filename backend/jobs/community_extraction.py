"""板块三特征抽取 job（M2，决策 v1.7 §4.6/§4.7）。

服务端抽取为唯一真源：从 learning_records / 计划任务计算授权用户的特征并 upsert 到
community_features。只落白名单指标（hours/focus/fatigue/completion）；stage 缺失不抽取；
completion 无计划任务不落该指标；focus/fatigue 取周期内最近一次自评（保持 1-5 整数）。

周期 = 当前 ISO 周（周一至周日），周日 23:59 统一抽取（§4.7 已拍板时点）。
撤回后（enabled=false）用户不参与；特征行周期性物理删除（仅保留当周）。
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select

from anon_id import compute_anon_id
from config import settings
from database import SessionLocal
from models.community import CommunityFeature
from models.learning_record import LearningRecord
from models.plan import PlanTask as PlanTaskORM
from models.user import Settings as SettingsORM

logger = logging.getLogger(__name__)

ALLOWED_METRICS = ("hours", "focus", "fatigue", "completion")


def _current_iso_week() -> str:
    """当前 ISO 周（如 2026-W35）。"""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_bounds(period: str) -> tuple[date, date]:
    """ISO 周 → (周一, 周日)。"""
    year, week = int(period.split("-W")[0]), int(period.split("-W")[1])
    # ISO 周第一天的公式
    jan4 = date(year, 1, 4)
    monday = jan4 + timedelta(days=-(jan4.weekday()) + (week - 1) * 7)
    return monday, monday + timedelta(days=6)


def extract_community_features(db=None) -> dict:
    """抽取并 upsert 当周特征。返回 {participants, features} 统计。"""
    db = db or SessionLocal()
    own = db is None
    stats = {"participants": 0, "features": 0}
    try:
        period = _current_iso_week()
        start, end = _week_bounds(period)
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        # 只抽已授权且资料完整（有 stage）的建档用户
        users = db.execute(
            select(SettingsORM.user_id)
            .where(SettingsORM.community_consent_enabled.is_(True))
        ).scalars().all()
        # stage 从 User 表读取（未建档/缺 stage 用户跳过）
        from models.user import User as UserORM

        for (uid,) in users:
            u = db.get(UserORM, uid)
            if u is None or not u.onboarding_completed or u.stage not in ("junior", "senior"):
                continue  # stage 缺失不抽取（§4.6）
            recs = db.execute(
                select(LearningRecord)
                .where(
                    LearningRecord.user_id == uid,
                    LearningRecord.started_at >= start_dt,
                    LearningRecord.started_at <= end_dt,
                )
                .order_by(LearningRecord.started_at.desc())
            ).scalars().all()
            if not recs:
                continue

            anon = compute_anon_id(uid)

            # hours = 本周总时长（小时）
            hours = sum(r.duration_minutes for r in recs) / 60.0
            _upsert_feature(db, anon, period, u.stage, "hours", hours)

            # focus/fatigue = 最近一次自评（1-5 整数，不做均值）
            latest = recs[0]
            _upsert_feature(db, anon, period, u.stage, "focus", float(latest.self_report_focus))
            _upsert_feature(db, anon, period, u.stage, "fatigue", float(latest.self_report_fatigue))

            # completion = 挂靠计划任务的完成比例（无任务不落行）
            ratio = _plan_completion_ratio(db, uid, start_dt, end_dt)
            if ratio is not None:
                _upsert_feature(db, anon, period, u.stage, "completion", ratio)

            stats["participants"] += 1
            stats["features"] += 3 + (1 if ratio is not None else 0)

        db.commit()
    finally:
        if own and db is not None:
            db.close()
    return stats


def _upsert_feature(db, anon: str, period: str, stage: str, metric: str, value: float) -> None:
    """按 (anon, period, metric) upsert。"""
    row = db.execute(
        select(CommunityFeature).where(
            CommunityFeature.anon_participant_id == anon,
            CommunityFeature.period == period,
            CommunityFeature.metric == metric,
        )
    ).scalars().first()
    if row is None:
        db.add(CommunityFeature(
            id=f"cf_{uuid.uuid4().hex[:12]}",
            anon_participant_id=anon,
            salt_version=0,
            period=period,
            stage=stage,
            metric=metric,
            value=round(float(value), 4),
        ))
    else:
        row.value = round(float(value), 4)
        row.stage = stage


def _plan_completion_ratio(db, uid: str, start: datetime, end: datetime) -> float | None:
    """挂靠计划任务的完成比例；周期内无任务返回 None（不落行，§4.6）。

    口径：plan.plan_date 落在本周的任务（而非计划创建时间落本周）。
    """
    from models.plan import Plan as PlanORM

    plans = db.execute(
        select(PlanORM.id).where(
            PlanORM.user_id == uid,
            PlanORM.plan_date >= start.date(),
            PlanORM.plan_date <= end.date(),
        )
    ).scalars().all()
    if not plans:
        return None
    total = db.execute(
        select(func.count()).select_from(PlanTaskORM).where(
            PlanTaskORM.plan_id.in_(plans),
            PlanTaskORM.removed.is_(False),
        )
    ).scalar_one()
    if total == 0:
        return None
    completed = db.execute(
        select(func.count()).select_from(PlanTaskORM).where(
            PlanTaskORM.plan_id.in_(plans),
            PlanTaskORM.removed.is_(False),
            PlanTaskORM.status == "completed",
        )
    ).scalar_one()
    return round(completed / total, 4)


def rotate_period(db=None) -> None:
    """周期滚动：删除非当周的特征行（§4.5 物理删除，只保留当周）。"""
    db = db or SessionLocal()
    try:
        current = _current_iso_week()
        db.execute(delete(CommunityFeature).where(CommunityFeature.period != current))
        db.commit()
    finally:
        pass  # 连接由调用方管理（run_community_extraction 自开自关）


def run_community_extraction() -> dict:
    """后台入口：自开 session，物理删除过期行 + 抽取当周特征。"""
    from database import SessionLocal as SL

    db = SL()
    try:
        rotate_period(db)
        return extract_community_features(db)
    except Exception:  # noqa: BLE001 — job 异常不穿透
        logger.exception("[COMMUNITY] 特征抽取失败")
        return {"participants": 0, "features": 0}
    finally:
        db.close()

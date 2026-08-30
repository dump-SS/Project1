"""板块三群体参照：匿名聚合授权链路（M1）。

- GET /me/community-consent     读取授权状态（默认关闭）
- PUT /me/community-consent     开启/撤回；enabled=true 为显式授权（§4.7 每周自动参与，
                              由服务端抽取 job 按授权状态自动纳入当周数据）；enabled=false 为撤回：
                              物理删除该用户全部特征行 + 触发延迟重算（§4.5）。
- 监护人授权失效时写接口 403（§4.5）。
- 授权/撤回事件写审计留痕（§4.5，不含特征值）。
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import GuardianAuthorization as GuardianORM
from models.user import Settings as SettingsORM
from schemas.community import (
    CommunityAggregateResponse,
    CommunityConsent,
    CommunityConsentUpdate,
)
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/community-consent", tags=["用户与设置"])
aggregate_router = APIRouter(prefix="/community", tags=["群体参照"])


def _get_or_create_settings(db: Session, user_id: str) -> SettingsORM:
    s = db.get(SettingsORM, user_id)
    if s is None:
        s = SettingsORM(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _ensure_guardian_active(db: Session, user_id: str) -> None:
    """监护人授权失效 → 403（写接口阻断，§4.5）。无记录视为 pending 放行（由监护人链路另行处理）。"""
    g = db.get(GuardianORM, user_id)
    if g is not None and g.status in ("expired", "revoked"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "GUARDIAN_AUTHORIZATION_EXPIRED", "message": "监护人授权已过期，请重新确认后继续使用"},
        )


@router.get("", response_model=CommunityConsent, summary="读取匿名聚合授权状态")
def get_community_consent(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> CommunityConsent:
    s = _get_or_create_settings(db, _user.user_id)
    return CommunityConsent.model_validate({
        "enabled": s.community_consent_enabled,
        "autoParticipate": s.community_auto_participate,
        "updatedAt": s.updated_at,
    })


@router.put("", response_model=CommunityConsent, summary="开启 / 撤回匿名聚合授权")
def put_community_consent(
    body: CommunityConsentUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> CommunityConsent:
    _ensure_guardian_active(db, _user.user_id)

    s = _get_or_create_settings(db, _user.user_id)
    s.community_consent_enabled = body.enabled
    if body.auto_participate is not None:
        s.community_auto_participate = body.auto_participate
    s.updated_at = datetime.utcnow()
    db.commit()

    if body.enabled is False:
        # 撤回：物理删除该用户全部特征行（§4.5 选项 A），聚合重算留给聚合 job（延迟 ≤24h）
        _delete_user_features(db, _user.user_id)

    logger.info(
        "[COMMUNITY_CONSENT] user=%s action=%s auto=%s",
        _user.user_id, "enable" if body.enabled else "revoke", s.community_auto_participate,
    )
    return CommunityConsent.model_validate({
        "enabled": s.community_consent_enabled,
        "autoParticipate": s.community_auto_participate,
        "updatedAt": s.updated_at,
    })


def _delete_user_features(db: Session, user_id: str) -> None:
    """物理删除用户全部特征行（§4.5 选项 A「撤回即删除」）。

    按 anon_participant_id = HMAC(user_id, salt) 定位，循环全部 salt_version
    （salt 轮换兼容，§4.5）：某版本盐算出的 ID 对应特征行一并删除。
    """
    from anon_id import compute_anon_id, SALT_VERSIONS
    from models.community import CommunityFeature

    for ver in SALT_VERSIONS:
        anon = compute_anon_id(user_id, salt_version=ver)
        db.execute(
            CommunityFeature.__table__.delete().where(
                CommunityFeature.anon_participant_id == anon
            )
        )
    db.commit()


# ---------- GET /community/aggregate（M3） ----------


def _check_agg_rate(db: Session, user_id: str) -> None:
    """聚合查询限频：每用户每分钟 5 次（§4.8），持久化到 rate_limit_counters。

    bucket_key 含分钟（community_agg:HH:MM），bucket_date 存当天，重启/多进程不丢。
    """
    from datetime import datetime as _dt

    from config import settings
    from models.rate_limit import RateLimitCounter

    now = _dt.utcnow()
    today = now.date()
    minute_key = f"community_agg:{now.hour:02d}:{now.minute:02d}"

    row = (
        db.query(RateLimitCounter)
        .filter(
            RateLimitCounter.user_id == user_id,
            RateLimitCounter.bucket_key == minute_key,
            RateLimitCounter.bucket_date >= _dt.combine(today, _dt.min.time()),
        )
        .first()
    )
    if row is None:
        row = RateLimitCounter(
            id=f"rl_{__import__('uuid').uuid4().hex[:12]}",
            user_id=user_id,
            bucket_key=minute_key,
            bucket_date=now,
            count=0,
        )
        db.add(row)
    if row.count >= settings.community_agg_rate_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "查询过于频繁，请稍后再试"},
        )
    row.count += 1
    db.commit()


@aggregate_router.get(
    "/aggregate",
    response_model=CommunityAggregateResponse,
    summary="当前周期群体聚合统计（只发聚合，不发个体）",
)
def get_community_aggregate(
    stage: str,
    metric: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> CommunityAggregateResponse:
    import json as _json

    from models.community import CommunityAggregate
    from jobs.community_aggregate import _current_iso_week

    # 402 请求维度校验（白名单）
    if stage not in ("junior", "senior"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "stage 仅支持 junior/senior", "field": "stage"},
        )
    if metric not in ("hours", "focus", "fatigue", "completion"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "metric 仅支持 hours/focus/fatigue/completion", "field": "metric"},
        )

    # 未授权 → 403（§4.9 未授权不返回任何聚合）
    s = db.get(SettingsORM, _user.user_id)
    if s is None or not s.community_consent_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "COMMUNITY_CONSENT_REQUIRED", "message": "开启匿名聚合授权后才能查看群体参照"},
        )

    _check_agg_rate(db, _user.user_id)

    period = _current_iso_week()
    row = db.execute(
        CommunityAggregate.__table__.select().where(
            CommunityAggregate.period == period,
            CommunityAggregate.stage == stage,
            CommunityAggregate.metric == metric,
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "COMMUNITY_INSUFFICIENT_POOL", "message": "群体数据积累中，暂不展示对比"},
        )

    return CommunityAggregateResponse.model_validate({
        "stage": row["stage"],
        "metric": row["metric"],
        "period": row["period"],
        "poolSize": row["pool_size"],
        "percentiles": _json.loads(row["percentiles"]),
        "histogram": _json.loads(row["histogram"]),
        "computedAt": row["computed_at"],
    })

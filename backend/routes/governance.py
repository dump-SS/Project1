"""pilot 运营与治理路由（G 板块）——报错接收 / 用量查询 / 违规留痕 / 奖章 / 埋点上报。

对应 openapi.yaml（G 板块增量，待 X0 评审）：
- GET  /me/usage          只读用量查询（月度，UsageLedgerList）
- POST /error-reports     报错接收（#46 两处入口共用的后端）
- GET  /me/medals         奖章列表（#49 最小版，只列已获得）
- GET  /me/violations     本人违规处置留痕（#43，透明可查）
- POST /analytics/events  埋点上报（D39 三块，结构化事件，不含对话原文流水）

口径：
- 全部用户作用域接口，不接收不下发 userId（资源以当前用户为作用域）。
- usage_ledger 与 AICallLog 分两套（#9）；这里只读 ledger，写入在 llm_provider 出口。
- 无支付/充值任何 UI 或接口（支付整体推迟到 pilot 后）。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.governance import ErrorReport as ErrorReportORM
from models.governance import Medal as MedalORM
from models.governance import UsageLedger as UsageLedgerORM
from models.governance import ViolationLog as ViolationLogORM
from schemas.governance import (
    AnalyticsEvent,
    AnalyticsEventCreate,
    ErrorReport,
    ErrorReportCreate,
    Medal,
    MedalList,
    UsageLedgerEntry,
    UsageLedgerList,
    ViolationLog,
    ViolationLogList,
)
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pilot 运营与治理"])

# 埋点/报错 context 的序列化体积上限（防滥用；超限丢弃结构化体并留日志）
_CONTEXT_JSON_MAX = 8000


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _naive_utc(dt: datetime) -> datetime:
    """契约允许带时区的 date-time；库内统一存 naive UTC（与既有表口径一致）。"""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# --- 用量查询（只读；D38/#9） ---


@router.get(
    "/me/usage",
    response_model=UsageLedgerList,
    summary="只读用量查询（按月返回当前用户的模型数值成本流水与合计）",
)
def get_my_usage(
    month: str | None = Query(
        None,
        pattern=r"^\d{4}-\d{2}$",
        description="查询月份 YYYY-MM；缺省为当前月",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UsageLedgerList:
    """用量页数据源。只读，无任何支付/充值语义（支付推迟到 pilot 后）。"""
    if month is None:
        now = datetime.utcnow()
        month = f"{now.year:04d}-{now.month:02d}"
    year_str, mon_str = month.split("-")
    year, mon = int(year_str), int(mon_str)
    if not 1 <= mon <= 12:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_FAILED", "message": "month 月份非法", "field": "month"})
    start = datetime(year, mon, 1)
    end = datetime(year + (mon == 12), (mon % 12) + 1, 1)

    rows = (
        db.execute(
            select(UsageLedgerORM)
            .where(
                UsageLedgerORM.user_id == user.user_id,
                UsageLedgerORM.created_at >= start,
                UsageLedgerORM.created_at < end,
            )
            .order_by(UsageLedgerORM.created_at.asc())
        )
        .scalars()
        .all()
    )
    items = [
        UsageLedgerEntry(
            id=r.id,
            featureTier=r.feature_tier,
            reasoningTier=r.reasoning_tier,
            model=r.model,
            tokensIn=r.tokens_in,
            tokensOut=r.tokens_out,
            cost=r.cost,
            createdAt=r.created_at,
        )
        for r in rows
    ]
    return UsageLedgerList(
        items=items,
        totalCost=round(sum(i.cost for i in items), 6),
        totalTokensIn=sum(i.tokens_in for i in items),
        totalTokensOut=sum(i.tokens_out for i in items),
    )


# --- 报错接收（#46：设置常驻 + 消息级按钮，两处入口共用） ---


@router.post(
    "/error-reports",
    response_model=ErrorReport,
    status_code=status.HTTP_201_CREATED,
    summary="用户报错（设置常驻入口 messageId=null；消息级按钮带 messageId 与上下文）",
)
def create_error_report(
    payload: ErrorReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ErrorReport:
    """报错落库。context 只放结构化上下文（消息角色/意图等），**不含对话原文流水**。"""
    context_json = None
    if payload.context is not None:
        try:
            context_json = json.dumps(payload.context, ensure_ascii=False)
            if len(context_json) > _CONTEXT_JSON_MAX:
                logger.warning("[governance] 报错 context 超限（%d），丢弃", len(context_json))
                context_json = None
        except (TypeError, ValueError):
            context_json = None

    row = ErrorReportORM(
        id=_gen_id("er"),
        user_id=user.user_id,
        message_id=payload.message_id,
        intent=payload.intent,
        description=payload.description,
        context_json=context_json,
    )
    db.add(row)
    db.commit()

    return ErrorReport(
        id=row.id,
        messageId=row.message_id,
        intent=row.intent,
        description=row.description,
        context=payload.context if context_json is not None else None,
        createdAt=row.created_at,
    )


# --- 违规处置留痕（#43：分级处置必须留痕，本人可查） ---


@router.get(
    "/me/violations",
    response_model=ViolationLogList,
    summary="本人违规处置留痕（warn/temp_ban/perm_ban，按时间倒序）",
)
def get_my_violations(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ViolationLogList:
    rows = (
        db.execute(
            select(ViolationLogORM)
            .where(ViolationLogORM.user_id == user.user_id)
            .order_by(ViolationLogORM.created_at.desc())
        )
        .scalars()
        .all()
    )
    return ViolationLogList(
        items=[
            ViolationLog(
                id=r.id,
                level=r.level,
                action=r.action,
                reason=r.reason or "",
                createdAt=r.created_at,
            )
            for r in rows
        ]
    )


# --- 奖章（#49 最小版：5 个里程碑，不做积分商城/排行榜） ---


@router.get(
    "/me/medals",
    response_model=MedalList,
    summary="本人已获得奖章（里程碑枚举见 MedalMilestone；未获得的不返回）",
)
def get_my_medals(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MedalList:
    rows = (
        db.execute(
            select(MedalORM)
            .where(MedalORM.user_id == user.user_id)
            .order_by(MedalORM.awarded_at.asc())
        )
        .scalars()
        .all()
    )
    return MedalList(
        items=[
            Medal(medalId=r.id, milestone=r.milestone, awardedAt=r.awarded_at)
            for r in rows
        ]
    )


# --- 埋点上报（D39 三块：chat_interaction / ai_quality / profile_trace） ---


@router.post(
    "/analytics/events",
    response_model=AnalyticsEvent,
    status_code=status.HTTP_201_CREATED,
    summary="结构化埋点事件上报（不含对话原文流水；payload 入库前脱敏）",
)
def create_analytics_event(
    payload: AnalyticsEventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AnalyticsEvent:
    """前端/后端共用上报口。响应返回**脱敏后实际落库**的内容。"""
    from governance_service import track_event

    eid = track_event(
        user_id=user.user_id,
        category=payload.category.value,
        event_type=payload.event_type,
        session_id=payload.session_id,
        payload=payload.payload,
        occurred_at=_naive_utc(payload.occurred_at) if payload.occurred_at else None,
        db=db,
    )
    if eid is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_FAILED", "message": "埋点事件未通过校验（类别或载荷非法）"},
        )

    # ORM 与 schema 同名（AnalyticsEvent），用别名避开遮蔽
    from models.analytics import AnalyticsEvent as AnalyticsEventORM

    row = db.get(AnalyticsEventORM, eid)
    return AnalyticsEvent(
        id=row.id,
        category=row.category,
        eventType=row.event_type,
        sessionId=row.session_id,
        payload=json.loads(row.payload_json) if row.payload_json else None,
        occurredAt=row.occurred_at,
        createdAt=row.created_at,
    )

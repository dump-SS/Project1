"""带图出域门控（PRD 12.6 四道加固 ③ + A1 一次性确认，2026-11-27 Skyer 拍板）。

## 为什么需要这一层

`knowledge_ai_egress_enabled` 关闭时，``routes/search.py`` 会退回
``knowledge_aggregated`` 白名单、题面一个字都不出去——因为搜题有"纯本地/聚合"这个
降级态。**带图链路没有**：项目没有本地视觉模型，图片不出域就等于识别不了。

A1 因此把"关闭"定义为**本次请求需要一次性显式确认**，而不是直接禁用：

- 开关开 → 持久授权已存在，直接放行；
- 开关关 + ``X-Egress-Confirm: 1`` → 放行本次（单次授权），并留痕；
- 开关关 + 未确认 → **428** ``EGRESS_CONFIRM_REQUIRED``，前端据此弹确认框，
  用户点"继续"后带该头重试；勾"以后不用问"则同时 PATCH 打开开关。

## 为什么门控在路由层，不在 chat_engine / worksheet_extract

那两层拿不到 DB 会话与请求头，也没法把"需要确认"翻译成可重试的 HTTP 语义；
``chat_jobs`` 的 worker 更没有请求上下文——**重试必须在入队前完成**，
否则用户确认了也没法把已入队的任务重新带上授权。

## 与四道加固的对应

① 每次点击即一次授权：一次性确认就是用户当下点击，不是后台/定时任务；
② 境内服务商：沿用既有 provider，本模块不引入第二家；
③ 用户可关闭：读的就是设置页那个开关（默认 false）；
④ 出域留痕：放行时记 INFO（用户 / 场景 / 是否持久授权）。
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.user import Settings as SettingsORM

logger = logging.getLogger(__name__)

#: 一次性确认请求头（契约 docs/openapi.yaml v1.25.0 登记）
EGRESS_CONFIRM_HEADER = "X-Egress-Confirm"
#: HTTP 428 的错误码：前端按此码弹确认框并重试
EGRESS_CONFIRM_REQUIRED = "EGRESS_CONFIRM_REQUIRED"


def egress_switch_enabled(db: Session, user_id: str) -> bool:
    """读用户出域开关。**查不到设置行 = 关闭**（与 search.py 同口径，默认保守）。"""
    row = db.get(SettingsORM, user_id)
    return bool(row and row.knowledge_ai_egress_enabled)


def is_confirmed(raw_header: str | None) -> bool:
    """``X-Egress-Confirm: 1`` 视为本次已确认；其它值一律算未确认。"""
    return (raw_header or "").strip() == "1"


def require_egress_consent(
    db: Session, user_id: str, *, confirmed: bool, scene: str
) -> None:
    """开关关时要求本次带图请求显式确认。

    Args:
        scene: 调用点标识（``chat_media`` / ``worksheet_extract`` / ``media_summary``），
            只进日志，不下发给前端——前端文案统一，不按场景分叉。

    Raises:
        HTTPException: 428 ``EGRESS_CONFIRM_REQUIRED``。**刻意不用 403**：403 在本项目
            已承载"监护人授权失效 / 越权资源"，混用会让前端分不清该弹确认框还是该
            跳授权页。428 的语义就是"先满足前置条件再重试"。
    """
    if egress_switch_enabled(db, user_id):
        logger.info("[EGRESS] 持久授权放行 scene=%s user=%s", scene, user_id)
        return
    if confirmed:
        logger.info("[EGRESS] 单次确认放行 scene=%s user=%s", scene, user_id)
        return
    logger.info("[EGRESS] 需要一次性确认 scene=%s user=%s", scene, user_id)
    raise HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail={
            "code": EGRESS_CONFIRM_REQUIRED,
            "message": "这一步会把照片发给 AI 识别，需要你确认后继续",
            "field": "egressConfirm",
        },
    )

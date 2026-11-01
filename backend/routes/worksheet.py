"""D55 · 作业单照片抽取路由（POST /f/worksheet/extract，契约 v1.15.0）。

职责与 routes/chat.py 的媒体路径同构：
1. **归属校验**：复用 ``f_media._assert_owner``（同包，不跨层）——非本人 key 403、
   路径穿越 403，不触达 R2 也不触达 LLM。
2. **按 key 取回字节**：与 chat 的「降级为纯文本」不同，抽取没有降级态——
   图读不到就直接 404 / 503 / 502（契约里这三档就是这么分的）。
3. **调 LLM 抽取**：失败映射 502 ``EXTRACT_FAILED``，message 可直接展示给用户。

⚠️ 合规：本路由会把用户作业单照片字节送第三方 LLM（用户内容出域），与带图 Chat
同一口径妥协（data_class=state_plan，见 docs/openapi.yaml v1.12.0 段）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import r2_storage
from r2_storage import R2Error, R2NotConfigured
from routes.deps import current_user
from routes.f_media import _assert_owner
from schemas.user import User
from schemas.worksheet import WorksheetExtractRequest, WorksheetExtraction
from worksheet_extract import WorksheetExtractError, extract_worksheet_items

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/f/worksheet", tags=["F 板块·媒体"])


@router.post(
    "/extract",
    response_model=WorksheetExtraction,
    summary="作业单照片抽取作业项（LLM 视觉，会话内不落库）",
)
def extract_worksheet(
    body: WorksheetExtractRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorksheetExtraction:
    _assert_owner(body.media_key, user.user_id)

    # 取回字节：与 chat 的降级不同，抽取没有降级态，按契约分档报错
    try:
        data, mime = r2_storage.get_object(body.media_key)
    except R2NotConfigured:
        logger.warning("[WORKSHEET] R2 未配置，无法抽取 user=%s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "对象存储未配置，暂时无法识别作业单"},
        )
    except R2Error as e:
        if getattr(e, "status", None) == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "图片不存在或已被删除"},
            )
        logger.warning("[WORKSHEET] 取图失败 user=%s status=%s", user.user_id, e.status)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "EXTRACT_FAILED", "message": "这次没能读取照片，请重试一次"},
        )

    try:
        return extract_worksheet_items(data, mime, user.user_id)
    except WorksheetExtractError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "EXTRACT_FAILED", "message": str(e)},
        )

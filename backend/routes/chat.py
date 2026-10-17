"""Chat 真链路 API（B 板块 M1 最小真链路）。

POST /chat —— 发一条消息，返回真实回复 + 意图 + 可选卡片 + 当前会话/上下文栈状态。

边界：
- 单对话模型：无历史列表、无「新建对话」端点（D45 红线）
- 动作类请求（加题本/改画像/建目标）不在此直接执行，由模型出锚定确认卡

## mediaKey（F 板块识图，契约 v1.12.0）

请求可带一个**图片引用** ``mediaKey``（``POST /f/media`` 返回的 R2 key）。
本路由负责三件事，都是 web/bucket 层该做的：

1. **归属校验**：复用 ``f_media._assert_owner``（同包，不跨层）——非本人 key 直接 403，
   不触达 R2。**刻意不重写这条规则**：重写就会出现第二份「谁能删/看自己的图」的判定，
   迟早漂移。
2. **按 key 取回字节**：R2 读取是同步阻塞的（urllib 无异步版），而本路由是 ``def``
   同步路由，Starlette 会自动丢线程池，所以这里**不需要** ``asyncio.to_thread``。
3. **取图失败降级**：R2 挂了或对象已被删，**不让整轮问答失败**——降级为纯文本，
   并把「图片没读到」这个事实交给 chat_engine，由它要求模型照实告知用户。

⚠️ 合规：本路由会把用户图片字节经 provider 送去第三方 LLM，属于用户内容出域。
判断与依据见 ``docs/openapi.yaml`` info.description 的 v1.12.0 段（lead-1 判断，
**待 Skyer 复核**）。本轮按该判断**不挂** ``knowledge_ai_egress_enabled`` 门控，
与 ``routes/search.py`` 的同类路径口径不同——该不一致已在契约里显式记录。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import r2_storage
from chat_engine import greeting, handle_ephemeral, handle_message
from database import get_db
from schemas.chat import ChatGreeting, ChatMessageRequest, ChatReply
from schemas.user import User
from .deps import current_user
from .f_media import _assert_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/greeting", response_model=ChatGreeting, summary="回到 AI 页的问候语（#34，冷启动注入上次话题摘要）")
def get_greeting(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatGreeting:
    return greeting(db, _user.user_id)


def _load_media_for_chat(media_key: str, user_id: str) -> tuple[bytes, str] | None:
    """按 key 取回图片字节。**取不到就返回 None，绝不抛给整轮问答。**

    刻意不让取图失败冒泡成5xx：用户发了一张图、图暂时读不到，
    正确的表现是「这次我看不到图」而不是整轮对话报500。
    模型侧怎么表达这个降级，由 chat_engine 负责（它构造 prompt）。

    归属校验在这里之前已经由 :func:`_assert_owner` 做完，越权请求根本走不到这。
    """
    try:
        data, mime = r2_storage.get_object(media_key)
    except r2_storage.R2NotConfigured:
        logger.warning("[CHAT] R2 未配置，带图请求降级为纯文本 user=%s", user_id)
        return None
    except r2_storage.R2Error as e:
        # 404 = 图已被用户删掉；其他 = R2 侧故障。都不该让整轮失败。
        logger.warning("[CHAT] 取图失败，降级为纯文本 user=%s status=%s", user_id, e.status)
        return None
    logger.info("[CHAT] 取图成功 user=%s bytes=%d mime=%s", user_id, len(data), mime)
    return data, mime


@router.post("", response_model=ChatReply, summary="发送一条消息，获取助手真实回复")
def send_message(
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatReply:
    media = None
    if payload.media_key:
        # 归属校验先行：越权 key 在这里就403，且不触达 R2。
        _assert_owner(payload.media_key, _user.user_id)
        if payload.ephemeral:
            # 随手问是受限问答，刻意不支持附件。**显式拒绝而不是静默忽略**——
            # 静默忽略会让用户以为 AI 看到了图，正是本任务要消灭的行为。
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": "随手问浮窗暂不支持附件，请用主对话发送",
                    "field": "mediaKey",
                },
            )
        media = _load_media_for_chat(payload.media_key, _user.user_id)

    if payload.ephemeral:
        # 随手问浮窗（受限 Chat 基础问答，D51）：floatContext 携带浮窗内前几轮
        return handle_ephemeral(
            db,
            _user.user_id,
            payload.content,
            [t.model_dump() for t in payload.float_context],
        )
    return handle_message(
        db,
        _user.user_id,
        payload.content,
        payload.intent,
        media_key=payload.media_key,
        media=media,
    )
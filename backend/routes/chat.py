"""Chat 真链路 API（B 板块 M1 最小真链路）。

POST /chat —— 发一条消息，返回真实回复 + 意图 + 可选卡片 + 当前会话/上下文栈状态。

边界：
- 单对话模型：无历史列表、无「新建对话」端点（D45 红线）
- 动作类请求（加题本/改画像/建目标）不在此直接执行，由模型出锚定确认卡
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from chat_engine import greeting, handle_ephemeral, handle_message
from database import get_db
from schemas.chat import ChatGreeting, ChatMessageRequest, ChatReply
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/greeting", response_model=ChatGreeting, summary="回到 AI 页的问候语（#34，冷启动注入上次话题摘要）")
def get_greeting(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatGreeting:
    return greeting(db, _user.user_id)


@router.post("", response_model=ChatReply, summary="发送一条消息，获取助手真实回复")
def send_message(
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatReply:
    if payload.ephemeral:
        # 随手问浮窗（受限 Chat 基础问答，D51）：floatContext 携带浮窗内前几轮
        return handle_ephemeral(
            db,
            _user.user_id,
            payload.content,
            [t.model_dump() for t in payload.float_context],
        )
    return handle_message(db, _user.user_id, payload.content, payload.intent)
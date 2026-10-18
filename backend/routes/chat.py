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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

import r2_storage
from chat_engine import greeting, handle_ephemeral, handle_message
from chat_jobs import (
    MAX_ACTIVE_JOBS_PER_USER,
    POLL_AFTER_MS,
    count_active_jobs,
    new_job_id,
    run_chat_job,
    to_schema,
)
from database import get_db
from models.chat import ChatJob
from schemas.chat import (
    ChatGreeting,
    ChatJob as ChatJobSchema,
    ChatMediaJobAccepted,
    ChatMediaJobRequest,
    ChatMessageRequest,
    ChatReply,
)
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


# ---------------------------------------------------------------------------
# 带图异步（契约 v1.13.0）
#
# 为什么**另开一个端点**而不是给 /chat 加个 ?async=1：
# 纯文本 tier=chat 的 tokens_out 只有 5~107，延迟远低于带图。为了带图的慢把整个
# Chat 改成异步，会让绝大多数对话体验变差、还要大改前端。带图是少数派路径，
# 就该走少数派的端点——同步 /chat 的响应形状一字未改。
# ---------------------------------------------------------------------------


@router.post(
    "/media",
    response_model=ChatMediaJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="发送一条带图消息，立即入队并返回 jobId（异步）",
)
def send_media_message_async(
    payload: ChatMediaJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatMediaJobAccepted:
    """入队一个带图任务，**立即返回 202**；结果用 ``GET /chat/jobs/{jobId}`` 轮询。

    归属校验 / 429 上限 / 失败语义都刻意与同步路径共用同一套口径，不另立规则。
    """
    # 1) 归属校验先行：越权 key 在这里就 403，且**不触达 R2**。
    #    与同步路径复用同一个 _assert_owner，不重写——重写就会出现第二份
    #    「谁能用自己的图」的判定，迟早漂移。
    _assert_owner(payload.media_key, _user.user_id)

    # 2) 并发上限：带图任务每跑一个就占住一个 worker 线程 + 一条 100~250 秒的
    #    LLM 长连接。不设上限的话，一个连发 20 张图的用户就能占满槽位，
    #    把**别的用户**的带图提问全堵在后面。宁可明确 429，也不要静默吞掉
    #    他刚拍的照片（详见 chat_jobs.MAX_ACTIVE_JOBS_PER_USER 的注释）。
    if count_active_jobs(db, _user.user_id) >= MAX_ACTIVE_JOBS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "TOO_MANY_MEDIA_JOBS",
                "message": "你还有带图提问在处理中，请稍后再试",
            },
        )

    # 3) 落库再入队。**顺序不能反**：状态行先提交，BackgroundTasks 才会执行。
    #    若先入队后提交，worker 可能在提交前就去 get(job_id) 拿到 None。
    job = ChatJob(
        id=new_job_id(),
        user_id=_user.user_id,
        status="queued",
        content=payload.content,
        media_key=payload.media_key,
    )
    db.add(job)
    db.commit()
    db.refresh(job)  # created_at 是 server_default，需要回读

    background_tasks.add_task(run_chat_job, job.id)

    return ChatMediaJobAccepted(
        status="queued",
        jobId=job.id,
        pollAfterMs=POLL_AFTER_MS,
        acceptedAt=job.created_at,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=ChatJobSchema,
    summary="轮询带图 Chat 任务状态",
)
def get_chat_job(
    job_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> ChatJobSchema:
    """查一个带图任务。拿到 ``done`` / ``failed`` 后前端必须停止轮询。"""
    job = db.get(ChatJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "任务不存在"},
        )
    # 与 /f/media 同一套口径：越权用 403 而非 404，因为语义是「你无权访问」，
    # 不是「资源不存在」；用 404 会让前端分不清该重试还是该放弃。
    if job.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "无权访问该任务"},
        )
    return to_schema(job)
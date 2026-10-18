"""带图 Chat 异步任务的 worker 与启动对账（契约 v1.13.0）。

对应 openapi.yaml `POST /chat/media` + `GET /chat/jobs/{jobId}`。
入口在 `routes/chat.py`，本模块只管「拿到 jobId 之后的事」。

## 为什么是 BackgroundTasks 而不是队列中间件

brief 里的「进程内队列 + 轮询」有三种落地方式：asyncio.Queue、BackgroundTasks、
Redis/Celery/arq。本项目选 **BackgroundTasks + DB 状态行**，理由：

1. **已有同构先例**：`routes/recommendation.py:72-107` 的「202 + pending 行 +
   BackgroundTasks」和 `ai_suggestion.py:610-634` 的 worker（自开 SessionLocal、
   异常置 failed）就是这个形状，平移过来等于零新概念、零新运维面。
2. **不引新依赖**：Redis/Celery/arq 会给 pilot 阶段凭空加一个必须运维的有状态服务。
   带图任务**丢得起**（用户重发一次就行），不值得为它引入一个必须保证不挂的组件。
3. **真正的瓶颈不是排队，是模型延迟**：实测单次中位 105.7s、最大 245.8s，
   瓶颈 100% 在 LLM 调用上，不在排队。换成 Kafka 也一样要等那 105 秒。

⚠️ BackgroundTasks 的已知边界（这是它与真队列的唯一实质差别，**不隐瞒**）：
任务只活在**当前实例内存**里。所以状态必须落库，且必须有启动对账——
否则实例一重启，用户手里的 jobId 会永远停在 `processing`，对着转圈圈等到天亮。
这正是 `reconcile_on_startup()` 存在的理由。

## 重启后怎么办：置 failed，不静默重跑

残留的 queued/processing 一律置 `failed` + `CHAT_JOB_INTERRUPTED`，**不自动重跑**：

- 带图推理单次要 100~250 秒，重启往往是部署/崩溃造成的，立刻重跑等于把重启
  风暴放大成 LLM 账单风暴；
- 更重要的是**诚实**：任务确实没跑完，用户该知道"这次没成，请再试"，
  而不是等一个永远不会来的结果。契约把 `CHAT_JOB_INTERRUPTED` 列为公开
  errorCode 就是为了这个。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.chat import CHAT_JOB_ACTIVE_STATUSES, ChatJob
from schemas.chat import ChatJob as ChatJobSchema

logger = logging.getLogger(__name__)

#: 同一用户允许的「在途」带图任务上限（queued + processing）。
#:
#: 为什么设上限而不是无限排队：带图任务每跑一个就占住一个实例的 worker 线程 +
#: 一条 LLM 长连接（实测 100~250 秒）。不设上限的话，一个连发 20 张图的用户
#: 就能把并发槽位占满，**别的用户**的带图提问全排在他后面——这是典型的
#: 「无界队列把噪声放大成全局阻塞」。超限时直接 429 让他知道，而不是静默吞掉
#: 他刚拍的照片。
MAX_ACTIVE_JOBS_PER_USER = 4

#: 下发给前端的建议轮询间隔。前端不写死，调节奏不用重新发布前端。
POLL_AFTER_MS = 2000

#: 失败原因码（契约 ChatJob.errorCode 的取值集合）
ERR_INTERNAL = "CHAT_JOB_INTERNAL_ERROR"
ERR_INTERRUPTED = "CHAT_JOB_INTERRUPTED"

#: 面向用户的失败文案。刻意不给技术细节：内部异常栈不该出现在学生面前，
#: 但也绝不能是「操作失败，请重试」这种无信息量的话。
ERR_MESSAGE_INTERNAL = "处理带图提问时出错了，请再试一次"
ERR_MESSAGE_INTERRUPTED = "服务刚刚重启，这次带图提问没有跑完，请再发一次"


def count_active_jobs(db: Session, user_id: str) -> int:
    """该用户当前在途（queued + processing）的带图任务数。"""
    stmt = select(func.count()).select_from(ChatJob).where(
        ChatJob.user_id == user_id,
        ChatJob.status.in_(CHAT_JOB_ACTIVE_STATUSES),
    )
    return int(db.execute(stmt).scalar_one())


def new_job_id() -> str:
    """job id：`cj_` + 12 位 hex，与契约 example 的形状一致。

    这里自己生成而不复用 `chat_engine._gen`：那是 chat_engine 的内部工具，
    而 job id 的形状是**对外契约**的一部分（前端会当不透明串用），应该由
    chat_jobs 自己拥有。
    """
    return f"cj_{uuid.uuid4().hex[:12]}"


def _loads(raw: str | None) -> list[Any]:
    """把 JSON 列读回列表；坏数据不拖垮整个响应。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("[CHAT-JOB] JSON 列解析失败，按空列表处理")
        return []
    return parsed if isinstance(parsed, list) else []


def to_schema(job: ChatJob) -> ChatJobSchema:
    """ORM 行 → 对外 schema。

    刻意不让 pydantic 直接从 ORM 读（没开 from_attributes）：结果列在库里是
    **JSON 字符串**，而契约要的是结构化数组，中间必须过一次 json.loads。
    """
    return ChatJobSchema(
        jobId=job.id,
        status=job.status,
        reply=job.reply,
        intent=job.intent,
        crisis=bool(job.crisis),
        cards=_loads(job.cards_json),
        sessionId=job.session_id,
        contextStack=_loads(job.context_stack_json),
        errorCode=job.error_code,
        errorMessage=job.error_message,
        createdAt=job.created_at,
        completedAt=job.completed_at,
    )


def reconcile_on_startup() -> int:
    """把上一实例遗留的 queued/processing 置为 failed，返回受影响行数。

    由 `main.py` 的 lifespan 调用。**幂等**：已经终态的行不会被碰，
    所以重复调用（多 worker 同时启动）安全。
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        stmt = select(ChatJob).where(ChatJob.status.in_(CHAT_JOB_ACTIVE_STATUSES))
        rows = list(db.execute(stmt).scalars())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for job in rows:
            job.status = "failed"
            job.error_code = ERR_INTERRUPTED
            job.error_message = ERR_MESSAGE_INTERRUPTED
            job.completed_at = now
        db.commit()
        if rows:
            logger.warning(
                "[CHAT-JOB] 启动对账：%d 个带图任务因实例重启被置为 failed "
                "（不自动重跑，避免把重启风暴放大成 LLM 账单风暴）",
                len(rows),
            )
        return len(rows)
    except Exception:
        db.rollback()
        logger.exception("[CHAT-JOB] 启动对账失败")
        raise
    finally:
        db.close()


def _mark_failed(db: Session, job: ChatJob, code: str, message: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_message = message
    job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def run_chat_job(job_id: str) -> None:
    """BackgroundTasks 入口：跑完一个带图 Chat 任务。

    自开 SessionLocal，**不复用请求 session**——本函数在响应返回之后才执行，
    请求 session 那时可能已经关闭（与 `ai_suggestion.run_recommendation_generation`
    同一个理由）。

    ⚠️ 吞掉所有异常是**故意的**：BackgroundTasks 里抛出的异常不会影响已经
    返回的 202，但 job 行会永远卡在 processing，用户只能干等。所以这里
    无论如何都要把行推到终态。
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(ChatJob, job_id)
        if job is None:
            # 理论上不该发生（job 行在入队时就提交了）。真发生了就是有人在
            # 手工调这个函数，如实记日志，不假装成功。
            logger.error("[CHAT-JOB] job 不存在 job_id=%s", job_id)
            return

        # 幂等：已经是终态就直接返回。避免重复投递把 done 覆盖成 failed。
        if job.status not in CHAT_JOB_ACTIVE_STATUSES:
            logger.info(
                "[CHAT-JOB] 已是终态，跳过 job_id=%s status=%s", job_id, job.status
            )
            return

        job.status = "processing"
        db.commit()
        logger.info("[CHAT-JOB] 开始执行 job_id=%s user=%s", job_id, job.user_id)

        try:
            # 取图放在 worker 里而不是路由里：R2 读取是同步阻塞的，而 BackgroundTasks
            # 在 sync 路由下已经在线程池里跑，不需要再 to_thread。
            from routes.chat import _load_media_for_chat

            media = _load_media_for_chat(job.media_key, job.user_id)

            from chat_engine import handle_message

            reply = handle_message(
                db,
                job.user_id,
                job.content,
                None,
                media_key=job.media_key,
                media=media,
            )

            job.reply = reply.reply
            job.intent = reply.intent
            job.crisis = bool(reply.crisis)
            job.cards_json = json.dumps(
                [c.model_dump(mode="json") for c in reply.cards], ensure_ascii=False
            )
            job.session_id = reply.session_id
            job.context_stack_json = json.dumps(
                [s.model_dump(mode="json") for s in reply.context_stack],
                ensure_ascii=False,
            )
            job.status = "done"
            job.error_code = None
            job.error_message = None
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            logger.info(
                "[CHAT-JOB] 完成 job_id=%s reply_len=%d crisis=%s",
                job_id,
                len(reply.reply or ""),
                bool(reply.crisis),
            )
        except Exception as e:
            logger.exception("[CHAT-JOB] 执行失败 job_id=%s: %s", job_id, e)
            try:
                db.rollback()
                job = db.get(ChatJob, job_id)
                if job is not None and job.status not in ("done", "failed"):
                    _mark_failed(db, job, ERR_INTERNAL, ERR_MESSAGE_INTERNAL)
            except Exception:
                logger.exception("[CHAT-JOB] 置 failed 时二次异常 job_id=%s", job_id)
    finally:
        db.close()

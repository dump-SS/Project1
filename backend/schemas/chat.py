"""Chat 内核的 Pydantic schema（B 板块 M1 最小真链路）。

对应 docs/openapi.yaml 新增的 ChatMessageRequest / ChatReply / ChatCard /
ChatContextStackItem（与 components.schemas 里既有的 ChatContextStackItem 对齐）。

带图异步任务（契约 v1.13.0）另见文件末尾的 ChatMediaJobRequest /
ChatMediaJobAccepted / ChatJob。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageRequest(BaseModel):
    """用户发送的一条消息。intent 为可选的显式意图（按钮通道）。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"content": "帮我讲讲二次函数单调性", "intent": None}},
    )

    content: str = Field(..., min_length=1, max_length=4000, description="用户消息正文")
    intent: str | None = Field(
        None, description="显式意图（按钮通道）。空则走斜杠命令或模型裸判"
    )
    ephemeral: bool = Field(
        False,
        description="随手问浮窗（受限 Chat 基础问答，D51）：单轮继承主对话上下文，不入栈、不回流、不出卡；浮窗内多轮用 floatContext 传入",
    )
    float_context: list["FloatTurn"] = Field(
        default_factory=list,
        alias="floatContext",
        description="随手问浮窗内前几轮输入输出（多轮追问用），role 为 user / assistant",
    )
    media_key: str | None = Field(
        None,
        alias="mediaKey",
        max_length=512,
        description=(
            "本轮附带的题目图片**引用**（POST /f/media 返回的 R2 key，形如 "
            "user/{userId}/{uuid}.png）。只传 key、不传字节：图片绝不 base64 进 JSON "
            "请求体（会让请求体膨胀一个数量级，且把用户图片复制进日志/中间件）。"
            "后端按 key 取回字节再送模型。"
        ),
    )


class FloatTurn(BaseModel):
    """随手问浮窗内的单轮输入输出（多轮追问；不回流主对话）。"""

    model_config = ConfigDict(populate_by_name=True)

    role: str = Field(..., description="user / assistant")
    content: str = Field(..., max_length=4000, description="该轮文本")


class ChatCard(BaseModel):
    """结构化产物卡片（D22 卡片协议）。type 决定前端渲染：task_card / knowledge_point / confirmation。"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(..., description="卡片类型：task_card / knowledge_point / confirmation 等")
    title: str = Field(..., max_length=60, description="卡片标题（短）")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="结构化数据（注入模型上下文用）"
    )
    display: dict[str, Any] = Field(default_factory=dict, description="渲染数据")


class ChatContextStackItem(BaseModel):
    """上下文栈的一层（D36，对齐 openapi ChatContextStackItem）。栈顶 = 最近切走的事。"""

    model_config = ConfigDict(populate_by_name=True)

    branch_type: str = Field(..., alias="branchType", description="chat / task_draft / knowledge_help")
    intent: str | None = Field(None, description="进入分支时的意图判定")
    step: str | None = Field(None, description="分支内进行到哪一步")
    payload: dict[str, Any] | None = Field(None, description="挂起载荷（不含对话原文）")
    entered_at: datetime | None = Field(None, alias="enteredAt", description="入栈时间")


class ChatReply(BaseModel):
    """一次 Chat 的响应：真实文案 + 意图 + 可选卡片 + 会话/栈状态。"""

    model_config = ConfigDict(populate_by_name=True)

    reply: str = Field(..., description="助手回复文本")
    intent: str | None = Field(None, description="本轮解析出的意图")
    crisis: bool = Field(False, description="是否触发危机转介（L3）")
    cards: list[ChatCard] = Field(default_factory=list)
    session_id: str = Field(..., alias="sessionId", description="当前会话 id（单对话模型，跨请求稳定）")
    context_stack: list[ChatContextStackItem] = Field(
        default_factory=list, alias="contextStack", description="当前上下文栈（深度≤3）"
    )


class ChatGreeting(BaseModel):
    """回到 AI 页的问候语（#34）。冷启动时 summary 为上次话题摘要，供问候语动态填充。"""

    model_config = ConfigDict(populate_by_name=True)

    greeting: str = Field(..., description="问候语文案（骨架 + 动态填充后的成品）")
    summary: str | None = Field(None, description="上次话题摘要（冷启动生成为非空，否则 None）")
    is_cold_start: bool = Field(False, alias="isColdStart", description="是否为冷启动（离开超阈值）")
    show_greeting: bool = Field(True, alias="showGreeting", description="是否在 AI 页展示这条问候")


# ---------------------------------------------------------------------------
# 带图 Chat 异步任务（契约 v1.13.0）
#
# 为什么单独三个 schema 而不直接复用 ChatReply：
#   · ChatReply.session_id 是必填 str，异步任务在 done 之前根本没有会话 id；
#   · 异步任务还要表达「排队中 / 失败原因」，这两件事 ChatReply 都不承载。
# done 之后 ChatJob 的结果字段与 ChatReply 逐字段同义，前端可复用同一套渲染逻辑。
# ---------------------------------------------------------------------------


class ChatMediaJobRequest(BaseModel):
    """带图异步提问的请求体。

    与 ChatMessageRequest 只差两点：``mediaKey`` **必填**（本接口的意义就是带图），
    且不接受 ``ephemeral`` / ``floatContext`` / ``intent``——随手问那条受限问答链路
    保持同步，不参与异步。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "content": "这道题怎么做？",
                "mediaKey": "user/u_10237/2f1c9a7b8d3e4f5061728394a5b6c7d8.png",
            }
        },
    )

    content: str = Field(..., min_length=1, max_length=4000, description="用户消息正文")
    media_key: str = Field(
        ...,
        alias="mediaKey",
        min_length=1,
        max_length=512,
        description=(
            "本轮附带的题目图片**引用**（`POST /f/media` 返回的 R2 对象 key）。"
            "归属校验与同步 `/chat` 同一套：非本人 key 直接 **403**，不触达 R2。"
            "取图失败时任务仍会完成，回复里明确告知模型看不到图（降级语义不变）。"
        ),
    )


class ChatMediaJobAccepted(BaseModel):
    """入队成功。**202 只代表「已受理」，不代表已有结果。**"""

    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(
        ...,
        description="刚入队、尚未开始执行，恒为 queued；worker 取到后翻成 processing。",
    )
    job_id: str = Field(
        ..., alias="jobId", description="任务 id，用于 `GET /chat/jobs/{jobId}` 轮询。"
    )
    poll_after_ms: int = Field(
        ...,
        alias="pollAfterMs",
        description=(
            "**建议**的轮询间隔（毫秒），由服务端下发而不是写死在前端，"
            "这样调节奏不需要重新发布前端。拿到终态后前端必须停止轮询。"
        ),
    )
    accepted_at: datetime = Field(
        ..., alias="acceptedAt", description="入队时间（UTC）"
    )


class ChatJob(BaseModel):
    """带图 Chat 任务状态。

    ``done`` 时 ``reply`` / ``intent`` / ``crisis`` / ``cards`` / ``sessionId`` /
    ``contextStack`` 与同步 ChatReply 逐字段同义，前端可走同一套渲染逻辑。
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(..., alias="jobId")
    status: str = Field(
        ...,
        description=(
            "queued 已入队待执行；processing 执行中；done 成功；failed 失败。"
            "**后两者是终态，前端必须停止轮询。**"
        ),
    )
    reply: str | None = Field(None, description="助手回复正文；status != done 时为 None")
    intent: str | None = Field(None, description="本轮解析出的意图；status != done 时为 None")
    crisis: bool = Field(False, description="是否触发危机转介")
    cards: list[ChatCard] = Field(default_factory=list, description="结构化卡片")
    session_id: str | None = Field(
        None, alias="sessionId", description="当前会话 id；status != done 时为 None"
    )
    context_stack: list[ChatContextStackItem] = Field(
        default_factory=list, alias="contextStack", description="当前上下文栈（深度封顶 3）"
    )
    error_code: str | None = Field(
        None,
        alias="errorCode",
        description=(
            "失败原因码（status=failed 时非空），前端据此给用户明确提示，"
            "**不允许用户干等**。取值 CHAT_JOB_INTERNAL_ERROR（worker 内部异常）、"
            "CHAT_JOB_INTERRUPTED（实例重启，任务被启动对账置为失败）。"
        ),
    )
    error_message: str | None = Field(
        None,
        alias="errorMessage",
        description="面向用户的失败说明，可直接展示",
    )
    created_at: datetime = Field(..., alias="createdAt", description="入队时间")
    completed_at: datetime | None = Field(
        None, alias="completedAt", description="进入终态的时间；未完成时为 None"
    )
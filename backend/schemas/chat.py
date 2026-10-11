"""Chat 内核的 Pydantic schema（B 板块 M1 最小真链路）。

对应 docs/openapi.yaml 新增的 ChatMessageRequest / ChatReply / ChatCard /
ChatContextStackItem（与 components.schemas 里既有的 ChatContextStackItem 对齐）。
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
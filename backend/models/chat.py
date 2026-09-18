"""Chat 内核的持久化（B 板块）：会话与上下文栈、对话原文短期留存、画像、话题摘要。

对应 openapi.yaml `components.schemas.ChatSession / ChatRawMessage / UserProfileEntry / TopicSummary`。

设计要点（D2 / D36 / D45 / D50）：
- **单对话**：全产品只有一条持续演进的对话，**无历史列表、无「新建对话」**。
- **会话 = 一个连续使用周期**（D45），跨刷新 / 跨设备持久——服务端存，前端仅是视图。
  无交互超阈值 → 栈内上下文老化清空；**不采用每日零点重置**（23:59 聊到一半被清空
  不可接受）。会话与上下文栈拆两层：栈是瞬时状态，未完成的实体各自落库、各有 TTL。
- **对话原文短期留存**（§3.8.3）：产品上不给任何回看入口（无列表 / 搜索 / 导出），
  只服务安全审计与异常排查——L3 危机响应需要事后可追溯，完全不存对未成年产品是反向
  风险。不入画像，到期由 TTL job 物理删除。⚠️ 与「埋点存结构化事件」口径不同，不可混同。
- **画像（D50）是信任基础设施**：不做对话历史的前置条件就是「画像可看 / 可改 / 可删」。
  条目由模型隐式提取写入，用户**可改可删但不可手动新建**；四组按意图选组注入，不全量。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ChatSession(Base):
    """会话（单对话模型下用户通常只有一条活跃会话）。

    `context_stack_json` 存上下文栈（深度=3、LIFO，D36）：超限时最旧者按类型**沉降**——
    任务草稿转持久化中间态（进 Go on 组）、搜题/讲解转知识页归档、纯闲聊直接丢弃。
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # 最近交互时间：据此判断会话是否老化（阈值实现时定，建议 24h–7d、默认偏长）
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    # 上下文栈（JSON 文本）。栈是瞬时状态，老化即清空；沉降物不随会话老化。
    context_stack_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatRawMessage(Base):
    """对话原文短期留存（TTL）。产品不可见、不入画像、到期物理删除。"""

    __tablename__ = "chat_raw_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    # TTL 清除 job 据此物理删除（建议 7–30 天，窗口实现时定）
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class UserProfile(Base):
    """画像条目（D50）。四组：learning / state / attribution / interest。

    ⚠️ 列名用 `profile_group`——`group` 是 SQL 保留字，直接用会在迁移与查询里踩坑；
    契约层字段名仍是 `group`（见 openapi UserProfileEntry）。
    同一 (user_id, group, key) 只保留一条：模型再次提取到同 key 时**覆盖**而非新增。
    """

    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "profile_group", "key", name="uq_user_profile_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_group: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    # 提取后的结构化值（非原始流水），如「薄弱知识点=函数/单调性」
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # explicit=用户显式填写 / inferred=模型推断 / self_report=自评叙事轨
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TopicSummary(Base):
    """跨登录话题摘要（#34）。会话结束生成 2–3 条，不存原文。

    它是首页问候语「预设骨架 + 动态填充」中**动态内容的唯一数据源**。
    """

    __tablename__ = "topic_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(512), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

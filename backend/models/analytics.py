"""埋点事件（analytics_events）—— G 板块 / D39 / §8。

对应 openapi.yaml `components.schemas.AnalyticsEvent`。

设计要点：
- D39 三块埋点统一落本表，用 `category` 区分：`chat_interaction`（Chat 交互）、
  `ai_quality`（AI 质量反馈）、`profile_trace`（画像 trace）。
- ⚠️ **与对话原文的口径划分**（§3.8.3 与 §8 反复强调，不可混同）：
  本表存的是**结构化事件**（意图判定结果、卡片事件、锚定结果、提取事件……），
  **不含对话原文流水**；原文是 `chat_raw_messages` 的短期安全留存（产品不可见、到期物理删除）。
- 敏感脱敏：入库前走 `privacy_filter`（§8 原则「聊天文本入库前脱敏」）。
- 埋点从「数据消费者」倒推，不为埋而埋；未成年产品克制 + 目的明确。
- `payload_json` 里**不放身份信息**（user_id 已在列上，脱敏后再进 payload）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # chat_interaction / ai_quality / profile_trace（D39 三块）
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 具体事件名，如 message_sent / card_shown / card_clicked / intent_corrected /
    # stack_pushed / stack_sunk / suggestion_read / explanation_rated / profile_extracted
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 关联会话（Chat 类事件用；其他类别可为空）
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # 结构化事件体（JSON 文本）。**不含对话原文流水**；入库前脱敏。
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 事件发生时间（前端上报的业务时间，与 created_at 的落库时间区分）
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

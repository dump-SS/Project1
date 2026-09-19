"""搜题归档（search_archives）—— D 板块 / §3.8.4 / D24 / D52。

对应 openapi.yaml `components.schemas.SearchArchive`。

为什么需要它（§3.8.4）：
D45 决定**不做对话历史**，用户看不到往日对话，于是很可能**重复问同一个知识点/同一道题**。
所以知识页的归档从「只有搜题归档」扩为「**搜题 + 讲解 归档**」——搜题（解一道题）与
讲解（讲透概念）是两条不同的链路，分别归档，不能用一个顶另一个。

合规口径（与 kb_errors 一致）：题面原文属 knowledge_raw，**只在本地留存、永不出域**，
embedding 必须走本地模型（PRD 12.6）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SearchArchive(Base):
    """一次搜题的结构化归档（题面 + 解答 + 关联知识点卡）。"""

    __tablename__ = "search_archives"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    # 题面原文（knowledge_raw：本地留存、永不出域）
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 解答正文（Markdown）
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 解题三态（D24）：direct=直给 / analytic=解析式 / guided=引导式。
    # 三态**记忆上次选择**，所以必须落库。
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # 结尾统一输出的知识点卡片（JSON 数组文本，元素为 {pointId, subjectCode, name, mastery?}）
    point_ids: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

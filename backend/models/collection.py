"""收藏（collections / collection_items）——D46 / D47 / #41 / #52。

对应 openapi.yaml `components.schemas.Collection / CollectionItem` 系列。
归属 E 板块（个人中心、收藏、社区与设置）。

设计要点：
- **必须存快照（D46）**：D45 决定不存对话历史、原文只做短期留存，所以收藏若只存
  引用，原文一到期就变成一堆死链。`snapshot_json` 存收藏当时的正文；图片圈选的收藏
  必须存裁剪后的小图（引用放在快照里，原图不留存）。
- 归位（D47）：**可评测的归知识页（题本），不可评测的归个人中心（收藏）**。
  收藏不进知识点库、不参与 mastery / 难度 / 图谱。
- 分组正交：内置分组（学科 / 时间 / 掌握度）是**筛选维度、不入表**；
  `collections` 是用户自定义分组标签，两者不打架。
- 内容不可编辑，但支持高亮与「虚化」（blur，用于隐藏信息或自测填空），
  虚化状态必须持久化（#41）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Collection(Base):
    """收藏的自定义分组（用户自建，如「计划」「闲聊」）。"""

    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CollectionItem(Base):
    """收藏条目。快照与各类标记统一存 JSON 文本列（避免为展示细节反复改表）。"""

    __tablename__ = "collection_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 自定义分组；未分组为 NULL（内置维度是筛选维度，不落列）
    collection_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ⚠️ 快照：收藏时的正文 + 可选裁剪小图引用。不存引用，存内容本体。
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源引用（仅用于溯源标注：来自哪条消息 / 哪次讲解 / 哪个知识点）
    source_ref_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 划选高亮区间
    highlight_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 「虚化」区间（持久化，否则每次重设）
    blur_state_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

"""讲解归档（explanations）——D 板块 / D52 / #22。

对应 openapi.yaml `components.schemas.Explanation`。

设计要点（D52）：
- **回顾取原文（original）+ 重讲现生成（regenerated）两者并存**，不要用一个顶掉另一个：
  重生成保证不了一致性（模型有随机性），而讲解的价值恰恰在「上次那个讲法、那个例子」。
- **精品样例（is_curated=true）预制入库、长期保存**，与动态生成严格区分；
  pilot 做 3–5 个，用于验证 schema 与生成管线。
- 无对话历史后（D45），用户很可能重复问同一个知识点，所以讲解必须归档，
  与「搜题归档」合并为知识页的「搜题 + 讲解归档」。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Explanation(Base):
    __tablename__ = "explanations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 库外知识为 NULL：只进画像归因，**不硬塞进 mastery**（#40b）
    point_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # original=回顾取原文 / regenerated=重新讲现生成
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="original")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 精品标记：true 表示预制入库的样例（长期保存，与动态生成区分）
    is_curated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

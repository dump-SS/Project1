"""首页推荐卡的展示记录（card_impressions）—— E 板块 / D21 / D28。

对应 openapi.yaml `components.schemas.CardImpression`。

为什么需要它（D28）：
推荐卡的生成规则里有**去重指纹 + 冷却**：
- Go on 组：划掉后 **3 天**不推（指纹 = planId / recordId）
- 推荐组：**7 天**不重复，且只推「有变化」的（指纹 = type + pointId / subject）
- 洞察组：**每周 ≤1**，同维度周内不重复（指纹 = 维度 + 周期）

没有「已展示过什么」的记录，冷却与去重就无从判断——这条规则本身依赖本表。
`recommendations` 表的语义是「AI 生成的建议」，与「卡片展示事件」不是一回事，故单独建表。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CardImpression(Base):
    """一次卡片展示 / 点击 / 划掉事件（冷却与去重的依据）。"""

    __tablename__ = "card_impressions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # go_on / recommend / insight（D21 三组）
    group: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # 卡面类型（D22 卡片协议）：continue_plan / state_advice / content_advice /
    # goal_planning / group_insight
    card_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # 去重指纹：Go on 用 planId/recordId；推荐用 type+pointId/subject；洞察用 维度+周期
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)

    # shown / clicked / dismissed（划掉 → 3 天不推）
    action: Mapped[str] = mapped_column(String(16), nullable=False, default="shown")

    shown_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

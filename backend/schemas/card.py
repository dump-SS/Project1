"""首页推荐卡（D21/D28）请求/响应模型 —— 契约 v1.21.0。

对应 openapi.yaml：CardGroup / CardAction / HomeCard / HomeCardGroupResult /
CardImpression / CardImpressionCreate（首次接后端实现）。

⚠️ 契约修复记录（2026-11-10，同版本内修正）：PR1 合并时 CardImpression 的正文
（description/required/properties）被错拼到 CardImpressionCreate 下面，YAML 重复键
导致 Create 的 required 实际解析成六字段（含 id/shownAt）。已把块移回宿主：
- CardImpressionCreate required = [group, cardType, fingerprint, action]（shownAt 可选，
  服务端记收到请求的时刻）；id/createdAt 由服务端生成
- CardImpression 响应体 required 保持六字段（响应本来就该全字段）
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import ConfigDict, Field

from schemas.common import APIModel


class CardGroup(str, Enum):
    """首页推荐卡三组（D21）：go_on=继续 / recommend=推荐 / insight=洞察。"""

    go_on = "go_on"
    recommend = "recommend"
    insight = "insight"


class CardAction(str, Enum):
    """shown=展示 / clicked=点击 / dismissed=划掉（划掉后 3 天不推）。"""

    shown = "shown"
    clicked = "clicked"
    dismissed = "dismissed"


class CardType(str, Enum):
    """D22 五类卡（target.md:172-180）。"""

    continue_plan = "continue_plan"
    state_advice = "state_advice"
    content_advice = "content_advice"
    goal_planning = "goal_planning"
    group_insight = "group_insight"


class HomeCardDisplay(APIModel):
    """展示层（用户看到的卡面）。"""

    title: str = Field(..., description="卡面主标题")
    subtitle: str | None = Field(None, description="卡面副标题（可省略）")


class HomeCardPayload(APIModel):
    """意图层（点击注入对话）。字段随 type 不同（契约 description 逐类说明）。

    refs/generated 是宽松 object —— 契约明确不强约束（PR1 已如实报备），
    各 type 的填充口径见 home_cards.py 的产卡 docstring。
    """

    refs: dict | None = Field(None, description="实体引用（精确）")
    generated: dict | None = Field(None, description="已生成摘要")
    instruction: str | None = Field(None, description="给模型的任务指令")


class HomeCard(APIModel):
    """首页推荐卡（D22 两层结构）。"""

    type: CardType
    display: HomeCardDisplay
    payload: HomeCardPayload | None = None
    fingerprint: str = Field(
        ...,
        description=(
            "去重指纹（后端产卡时已算好，前端原样回填到 POST /me/card-impressions）。"
            "PR2 遗漏：此前只用于查冷却、没透传，response_model 会把未声明字段丢掉，"
            "前端拿不到指纹就无法上报 shown/dismissed，冷却链路断。v1.21.0 同版本内补全。"
        ),
    )


class HomeCardGroupResult(APIModel):
    """一组推荐卡。组顺序固定 Go on → 推荐 → 洞察；无内容的组不返回。"""

    group: CardGroup
    cards: list[HomeCard]


class CardImpressionCreate(APIModel):
    """事件上报请求体（shownAt 可省略，服务端以收到请求时刻为事件时间）。"""

    model_config = ConfigDict(populate_by_name=True)

    group: CardGroup
    card_type: CardType = Field(..., alias="cardType")
    fingerprint: str = Field(..., min_length=1, max_length=160)
    action: CardAction
    shown_at: datetime | None = Field(None, alias="shownAt", description="可省略；省略时服务端记请求时刻")


class CardImpressionOut(APIModel):
    """事件落库后的完整记录（id / createdAt 服务端生成）。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    group: CardGroup
    card_type: CardType = Field(..., alias="cardType")
    fingerprint: str
    action: CardAction
    shown_at: datetime = Field(..., alias="shownAt")
    created_at: datetime = Field(..., alias="createdAt")

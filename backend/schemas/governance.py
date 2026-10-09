"""pilot 运营与治理（openapi.yaml G 板块 schemas）

UsageFeatureTier / ReasoningTier / UsageLedgerEntry / UsageLedgerList
ViolationAction / ViolationLog / ViolationLogList
ErrorReport / ErrorReportCreate
MedalMilestone / Medal / MedalList
AnalyticsCategory / AnalyticsEvent / AnalyticsEventCreate

口径提醒（对应 models/governance.py 与 openapi 描述）：
- usage_ledger 只存数值，不存任何提示词或输出内容；与去身份化的 AICallLog 分两套（#9）。
- 违规分级：1 次警告 → 3 次临时封禁 → 永久，必须留痕（#43）。
- 报错两处入口（#46）：设置常驻 + 消息级按钮；context 不含对话原文流水。
- 奖章最小版（#49）：5 个里程碑，不做积分商城 / 排行榜。
- 埋点三块（D39）：chat_interaction / ai_quality / profile_trace；结构化事件，
  不含对话原文流水，payload 入库前经 privacy_filter 脱敏。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UsageFeatureTier(str, Enum):
    """功能档位（分档定价依据，D38）。新增档位属契约变更。"""

    chat = "chat"            # 对话式（用户主动发起、有感）
    embedded = "embedded"    # 嵌入式（建议/复盘/画像提取等，系统自动、无感，不进 credits）
    advanced = "advanced"    # 高级（L3 富交互仿真 / 多模态搜题）
    multimodal = "multimodal"  # 文件解析（F 板块）


class ReasoningTier(str, Enum):
    """推理等级（#33：quick / standard / deep，与 credits 扣费档位绑定）。"""

    quick = "quick"
    standard = "standard"
    deep = "deep"


class ViolationAction(str, Enum):
    warn = "warn"
    temp_ban = "temp_ban"
    perm_ban = "perm_ban"


class MedalMilestone(str, Enum):
    """pilot 最小版里程碑（#49）。禁止新增积分/商城/排行类。"""

    first_record = "first_record"          # 第一次学习记录
    streak_7_days = "streak_7_days"        # 连续 7 天记录
    first_summary = "first_summary"        # 第一次完成复盘
    first_goal_achieved = "first_goal_achieved"  # 第一个目标达成
    first_topic_book = "first_topic_book"  # 题本第一条


class AnalyticsCategory(str, Enum):
    """D39 三块埋点。"""

    chat_interaction = "chat_interaction"  # Chat 交互（消息/卡片/意图纠正/上下文栈/搜题交互）
    ai_quality = "ai_quality"              # AI 质量反馈（读完率/采纳率/有用性/纠错）
    profile_trace = "profile_trace"        # 画像 trace（提取与改删事件）


class UsageLedgerEntry(BaseModel):
    """按用户记录的模型数值成本（只存数值，不含内容）。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    feature_tier: UsageFeatureTier = Field(alias="featureTier")
    reasoning_tier: ReasoningTier | None = Field(None, alias="reasoningTier")
    model: str
    tokens_in: int = Field(alias="tokensIn")
    tokens_out: int = Field(alias="tokensOut")
    cost: float = Field(description="数值成本（内部计价，非对用户计费）")
    created_at: datetime = Field(alias="createdAt")


class UsageLedgerList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[UsageLedgerEntry]
    total_cost: float | None = Field(None, alias="totalCost")
    total_tokens_in: int | None = Field(None, alias="totalTokensIn")
    total_tokens_out: int | None = Field(None, alias="totalTokensOut")


class ViolationLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    level: int = Field(description="累计违规等级（1 起）")
    action: ViolationAction
    reason: str = Field(description="处置原因（命中类型，不含原文）")
    created_at: datetime = Field(alias="createdAt")


class ViolationLogList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ViolationLog]


class ErrorReportCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str | None = Field(None, alias="messageId")
    intent: str | None = None
    description: str = Field(max_length=2000, description="用户描述的问题")
    context: dict | None = Field(None, description="上下文快照（不含对话原文流水）")


class ErrorReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    message_id: str | None = Field(None, alias="messageId")
    intent: str | None = None
    description: str
    context: dict | None = None
    created_at: datetime = Field(alias="createdAt")


class Medal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    medal_id: str = Field(alias="medalId")
    milestone: MedalMilestone
    awarded_at: datetime = Field(alias="awardedAt")


class MedalList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[Medal]


class AnalyticsEventCreate(BaseModel):
    """埋点上报体。服务端生成 id / createdAt。"""

    model_config = ConfigDict(populate_by_name=True)

    category: AnalyticsCategory
    event_type: str = Field(alias="eventType", max_length=64)
    session_id: str | None = Field(None, alias="sessionId")
    payload: dict | None = Field(None, description="结构化事件体（不含对话原文流水；入库前脱敏）")
    occurred_at: datetime | None = Field(None, alias="occurredAt")


class AnalyticsEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    category: AnalyticsCategory
    event_type: str = Field(alias="eventType")
    session_id: str | None = Field(None, alias="sessionId")
    payload: dict | None = None
    occurred_at: datetime = Field(alias="occurredAt")
    created_at: datetime = Field(alias="createdAt")

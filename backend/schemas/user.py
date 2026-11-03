"""
用户与设置（openapi.yaml 1.x）

User / UserProfilePut / UserProfilePatch / Settings / SettingsUpdate
/ GuardianAuthorizationRequest
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Stage, Subject


class GuardianAuthorizationInfo(BaseModel):
    """openapi.yaml User.guardianAuthorization 字段。"""

    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(..., description="授权状态：active / pending / revoked / expired")
    expires_at: datetime | None = Field(None, alias="expiresAt", description="授权到期时间")


class User(BaseModel):
    """当前用户资料。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "userId": "u_10237",
                "stage": "senior",
                "grade": "高二",
                "subjects": ["SX", "YY", "WL"],
                "birthYear": 2010,
                "guardianAuthorization": {
                    "status": "active",
                    "expiresAt": "2026-09-10T00:00:00+08:00",
                },
                "onboardingCompleted": True,
            }
        },
    )

    user_id: str = Field(..., alias="userId", description="用户 ID")
    stage: Stage
    grade: str = Field(..., description='年级，如「初二」「高二」')
    subjects: list[Subject] = Field(..., min_length=1, max_length=9, description="学科列表")
    birth_year: int | None = Field(
        None,
        alias="birthYear",
        description="出生年份（激活式建档采集，D40）；历史数据为 null",
    )
    guardian_authorization: GuardianAuthorizationInfo = Field(
        ..., alias="guardianAuthorization", description="监护人授权状态"
    )
    onboarding_completed: bool = Field(..., alias="onboardingCompleted", description="是否已完成建档")


class UserProfilePut(BaseModel):
    """幂等建档请求体。stage / grade / subjects 必填；birthYear 由激活式建档采集（可空）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stage": "senior",
                "grade": "高二",
                "subjects": ["SX", "YY", "WL"],
                "birthYear": 2010,
            }
        }
    )

    stage: Stage
    grade: str = Field(..., description='年级，如「初二」「高二」')
    subjects: list[Subject] = Field(..., min_length=1, max_length=9)
    birth_year: int | None = Field(
        None,
        alias="birthYear",
        ge=1900,
        le=2100,
        description="出生年份（4 位）；未满 14 岁且授权未生效时 onboardingCompleted 保持 false（D41）",
    )


class UserProfilePatch(BaseModel):
    """局部更新请求体，字段全可选。"""

    model_config = ConfigDict(populate_by_name=True)

    stage: Stage | None = None
    grade: str | None = None
    subjects: list[Subject] | None = Field(None, min_length=1, max_length=9)
    birth_year: int | None = Field(
        None, alias="birthYear", ge=1900, le=2100, description="出生年份（4 位）"
    )


class ProfileGroup(str, Enum):
    """画像四组（openapi.yaml UserProfileGroup 枚举，契约 v1.15.0）。

    对照 product-redesign-target.md 第 929 行 D10：learning / state /
    attribution / interest。
    """

    LEARNING = "learning"
    STATE = "state"
    ATTRIBUTION = "attribution"
    INTEREST = "interest"


class UserProfileEntry(BaseModel):
    """单条画像条目（openapi.yaml UserProfileEntry，契约 v1.15.0）。

    对照 product-redesign-target.md 第 929 行 D10：四组（learning / state /
    attribution / interest），同一 (user_id, group, key) 只保留一条。
    """

    model_config = ConfigDict(populate_by_name=True)

    entry_id: str = Field(..., alias="entryId", description="条目 id")
    group: str = Field(
        ..., description="learning / state / attribution / interest"
    )
    key: str = Field(..., description="条目键，如「薄弱知识点」")
    value: str = Field(..., description="提取后的结构化值（非原始流水）")
    source: str | None = Field(
        None,
        description="explicit=用户显式填写 / inferred=模型推断 / self_report=自评叙事轨",
    )
    confidence: float | None = Field(
        None, description="推断置信度（显式来源为 null）"
    )
    source_ref: str | None = Field(
        None, alias="sourceRef", description="提取来源引用（会话 id / 消息 id）"
    )
    updated_at: datetime | None = Field(
        None, alias="updatedAt", description="条目最后更新时间"
    )


class UserProfileEntryUpdate(BaseModel):
    """局部更新画像条目（openapi.yaml UserProfileEntryUpdate，契约 v1.15.0）。

    只能改 value 与 group，**不能新建**（新建走 PUT 的幂等建档语义）。
    """

    model_config = ConfigDict(populate_by_name=True)

    value: str | None = Field(None, description="条目新值")
    group: str | None = Field(None, description="组变更（learning / state / attribution / interest）")


class UserProfileList(BaseModel):
    """某组全部画像条目（openapi.yaml UserProfileList，契约 v1.15.0）。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[UserProfileEntry] = Field(default_factory=list, description="该组下的条目列表")


class Settings(BaseModel):
    """用户设置。权重数值不通过任何用户侧接口暴露。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "aiWeightTuningEnabled": True,
                "sendTextToAI": False,
                "knowledgeAiEgressEnabled": False,
                "userContentEmbeddingApiEnabled": False,
                "experienceImprovementEnabled": False,
                "updatedAt": "2026-08-16T09:12:00+08:00",
            }
        },
    )

    ai_weight_tuning_enabled: bool = Field(..., alias="aiWeightTuningEnabled", description="默认 true")
    send_text_to_ai: bool = Field(..., alias="sendTextToAI", description="默认 false")
    knowledge_ai_egress_enabled: bool = Field(
        False, alias="knowledgeAiEgressEnabled", description="默认 false：知识复盘 AI 出域开关（PRD 12.6）"
    )
    user_content_embedding_api_enabled: bool = Field(
        False,
        alias="userContentEmbeddingApiEnabled",
        description=(
            "默认 false（opt-in）：用户内容（错题原文/作答/学习记录）embedding 是否允许走第三方 API"
            "（PRD 12.6 / D41）。关闭时恒定走本地模型，本地不可用则降级 name_fuzzy、不造数（D34），"
            "绝不自动改走 API。未满 14 周岁且监护人授权未生效的账号禁止开启（403）。"
            "撤回（置 false）不受授权状态限制。"
        ),
    )
    experience_improvement_enabled: bool = Field(
        False,
        alias="experienceImprovementEnabled",
        description="默认 false（opt-in）：将个人数据用于提升体验（#29b）",
    )
    updated_at: datetime = Field(..., alias="updatedAt")


class SettingsUpdate(BaseModel):
    """设置更新请求体，至少传一项。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"sendTextToAI": True}},
    )

    ai_weight_tuning_enabled: bool | None = Field(None, alias="aiWeightTuningEnabled")
    send_text_to_ai: bool | None = Field(None, alias="sendTextToAI")
    knowledge_ai_egress_enabled: bool | None = Field(None, alias="knowledgeAiEgressEnabled")
    user_content_embedding_api_enabled: bool | None = Field(
        None,
        alias="userContentEmbeddingApiEnabled",
        description="默认 false（opt-in）；开启后用户内容 embedding 可走第三方 API（PRD 12.6 / D41）",
    )
    experience_improvement_enabled: bool | None = Field(
        None, alias="experienceImprovementEnabled", description="默认 false（opt-in，#29b）"
    )

    @model_validator(mode="after")
    def _at_least_one(self) -> "SettingsUpdate":
        if (
            self.ai_weight_tuning_enabled is None
            and self.send_text_to_ai is None
            and self.knowledge_ai_egress_enabled is None
            and self.user_content_embedding_api_enabled is None
            and self.experience_improvement_enabled is None
        ):
            raise ValueError(
                "至少传一项（aiWeightTuningEnabled / sendTextToAI / knowledgeAiEgressEnabled / "
                "userContentEmbeddingApiEnabled / experienceImprovementEnabled）"
            )
        return self


class GuardianAuthorizationRequest(BaseModel):
    """监护人邮箱/手机号二选一必填（openapi.yaml GuardianAuthorizationRequest）。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"guardianEmail": "guardian@example.com"}},
    )

    guardian_email: str | None = Field(
        None, alias="guardianEmail", max_length=254, description="监护人邮箱"
    )
    guardian_phone: str | None = Field(
        None, alias="guardianPhone", max_length=32, description="监护人手机号"
    )

    @model_validator(mode="after")
    def _guardian_contact_required(self) -> "GuardianAuthorizationRequest":
        if not self.guardian_email and not self.guardian_phone:
            raise ValueError("监护人邮箱或手机号至少填一项")
        return self

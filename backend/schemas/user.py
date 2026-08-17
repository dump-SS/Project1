"""
用户与设置（openapi.yaml 1.x）

User / UserProfilePut / UserProfilePatch / Settings / SettingsUpdate
/ GuardianAuthorizationRequest
"""
from __future__ import annotations

from datetime import datetime

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
                "subjects": ["math", "english", "physics"],
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
    guardian_authorization: GuardianAuthorizationInfo = Field(
        ..., alias="guardianAuthorization", description="监护人授权状态"
    )
    onboarding_completed: bool = Field(..., alias="onboardingCompleted", description="是否已完成建档")


class UserProfilePut(BaseModel):
    """幂等建档请求体，字段全必填。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stage": "senior",
                "grade": "高二",
                "subjects": ["math", "english", "physics"],
            }
        }
    )

    stage: Stage
    grade: str = Field(..., description='年级，如「初二」「高二」')
    subjects: list[Subject] = Field(..., min_length=1, max_length=9)


class UserProfilePatch(BaseModel):
    """局部更新请求体，字段全可选。"""

    stage: Stage | None = None
    grade: str | None = None
    subjects: list[Subject] | None = Field(None, min_length=1, max_length=9)


class Settings(BaseModel):
    """用户设置。权重数值不通过任何用户侧接口暴露。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "aiWeightTuningEnabled": True,
                "sendTextToAI": False,
                "updatedAt": "2026-08-16T09:12:00+08:00",
            }
        },
    )

    ai_weight_tuning_enabled: bool = Field(..., alias="aiWeightTuningEnabled", description="默认 true")
    send_text_to_ai: bool = Field(..., alias="sendTextToAI", description="默认 false")
    updated_at: datetime = Field(..., alias="updatedAt")


class SettingsUpdate(BaseModel):
    """设置更新请求体，至少传一项。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"sendTextToAI": True}},
    )

    ai_weight_tuning_enabled: bool | None = Field(None, alias="aiWeightTuningEnabled")
    send_text_to_ai: bool | None = Field(None, alias="sendTextToAI")

    @model_validator(mode="after")
    def _at_least_one(self) -> "SettingsUpdate":
        if self.ai_weight_tuning_enabled is None and self.send_text_to_ai is None:
            raise ValueError("至少传一项（aiWeightTuningEnabled 或 sendTextToAI）")
        return self


class GuardianAuthorizationRequest(BaseModel):
    """监护人邮箱与手机号至少传一项（openapi.yaml minProperties: 1）。"""

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
    def _at_least_one(self) -> "GuardianAuthorizationRequest":
        has_email = bool(self.guardian_email and self.guardian_email.strip())
        has_phone = bool(self.guardian_phone and self.guardian_phone.strip())
        if not has_email and not has_phone:
            raise ValueError("guardianEmail 和 guardianPhone 至少传一项")
        return self

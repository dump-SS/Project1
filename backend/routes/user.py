"""
/me + /me/settings + /me/guardian-authorization + /guardian-authorization/confirm

第 2 步全部返回 mock。第 3 步接入 ORM + JWT。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from database import get_db
from mock_data import USER_MOCK
from models.user import Settings as SettingsModel
from schemas.user import (
    GuardianAuthorizationRequest,
    Settings,
    SettingsUpdate,
    User,
    UserProfilePatch,
    UserProfilePut,
)
from .deps import current_user

router = APIRouter(prefix="", tags=["用户与设置"])


def _get_or_create_settings(db: Session, user_id: str) -> SettingsModel:
    settings = db.get(SettingsModel, user_id)
    if settings is None:
        settings = SettingsModel(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _serialize_settings(settings: SettingsModel) -> Settings:
    return Settings.model_validate(
        {
            "aiWeightTuningEnabled": settings.ai_weight_tuning_enabled,
            "sendTextToAI": settings.send_text_to_ai,
            "updatedAt": settings.updated_at,
        }
    )


@router.get("/me", response_model=User, summary="获取当前用户资料")
def get_me(user: User = Depends(current_user)) -> User:
    return user


@router.put("/me", response_model=User, summary="初始化用户资料（幂等建档，字段全必填）")
def put_me(body: UserProfilePut, _user: User = Depends(current_user)) -> User:
    # mock 永远返回同一个示例用户
    return USER_MOCK


@router.patch("/me", response_model=User, summary="更新用户资料（局部更新，字段全可选）")
def patch_me(body: UserProfilePatch, _user: User = Depends(current_user)) -> User:
    return USER_MOCK


@router.get("/me/settings", response_model=Settings, summary="读取用户设置")
def get_settings(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Settings:
    settings = _get_or_create_settings(db, user.user_id)
    return _serialize_settings(settings)


@router.patch("/me/settings", response_model=Settings, summary="更新用户设置（至少传一项）")
def patch_settings(
    body: SettingsUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Settings:
    settings = _get_or_create_settings(db, user.user_id)
    if body.ai_weight_tuning_enabled is not None:
        settings.ai_weight_tuning_enabled = body.ai_weight_tuning_enabled
    if body.send_text_to_ai is not None:
        settings.send_text_to_ai = body.send_text_to_ai

    db.commit()
    db.refresh(settings)
    return _serialize_settings(settings)


@router.post(
    "/me/guardian-authorization",
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交监护人联系方式并发送确认请求",
)
def submit_guardian_authorization(
    body: GuardianAuthorizationRequest,
    _user: User = Depends(current_user),
):
    # mock：校验由 Pydantic 自动完成，路由仅占位
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete(
    "/me/guardian-authorization",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="撤销监护人授权（账号进入只读）",
)
def revoke_guardian_authorization(_user: User = Depends(current_user)) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/guardian-authorization/confirm",
    summary="监护人点击链接确认授权（无需登录）",
)
def confirm_guardian_authorization(token: str = Path(...)) -> dict[str, bool]:
    # 真实实现：查 token → 标记 active → 写 sessions；mock 直接返回成功
    return {"ok": True}

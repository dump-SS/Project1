"""
/me + /me/settings + /me/guardian-authorization + /guardian-authorization/confirm

阶段 3（已接入）：/me 系列与 guardian 系列全部接 ORM，不再返 mock 常量。
- GET /me：读 ORM User + GuardianAuthorization 组装响应
- PUT /me：幂等建档（字段全必填），落库 + 置 onboarding_completed=true
- PATCH /me：局部更新用户资料
- POST /me/guardian-authorization：落库 GuardianAuthorization（pending + token），返回 202
- DELETE /me/guardian-authorization：置 revoked（账号进入只读）
- GET /guardian-authorization/confirm：查 token → 置 active + expires_at（监护人点链接，无需登录）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import GuardianAuthorization as GuardianAuthorizationORM
from models.user import User as UserORM
from schemas.user import (
    GuardianAuthorizationRequest,
    Settings,
    SettingsUpdate,
    User,
    UserProfilePatch,
    UserProfilePut,
)
from .deps import _build_user_response, current_user

router = APIRouter(prefix="", tags=["用户与设置"])


# ---------- Settings（已接 ORM，保持不变） ----------

def _get_or_create_settings(db: Session, user_id: str):
    from models.user import Settings as SettingsModel
    settings = db.get(SettingsModel, user_id)
    if settings is None:
        settings = SettingsModel(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _serialize_settings(settings):
    return Settings.model_validate(
        {
            "aiWeightTuningEnabled": settings.ai_weight_tuning_enabled,
            "sendTextToAI": settings.send_text_to_ai,
            "knowledgeAiEgressEnabled": settings.knowledge_ai_egress_enabled,
            "updatedAt": settings.updated_at,
        }
    )


# ---------- /me ----------

@router.get("/me", response_model=User, summary="获取当前用户资料")
def get_me(user: User = Depends(current_user)) -> User:
    return user


@router.put("/me", response_model=User, summary="初始化用户资料（幂等建档，字段全必填）")
def put_me(
    body: UserProfilePut,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> User:
    """幂等建档：用户不存在则创建，存在则覆盖（PUT 语义）。"""
    row = db.get(UserORM, user.user_id)
    if row is None:
        row = UserORM(
            id=user.user_id,
            stage=body.stage.value,
            grade=body.grade,
            subjects=[s.value for s in body.subjects],
            onboarding_completed=True,
        )
        db.add(row)
    else:
        row.stage = body.stage.value
        row.grade = body.grade
        row.subjects = [s.value for s in body.subjects]
        row.onboarding_completed = True
    db.commit()
    return _build_user_response(db, user.user_id)


@router.patch("/me", response_model=User, summary="更新用户资料（局部更新，字段全可选）")
def patch_me(
    body: UserProfilePatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> User:
    """局部更新。用户未建档时 404（PATCH 语义要求资源已存在）。"""
    from fastapi import HTTPException

    row = db.get(UserORM, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "用户尚未建档，请先 PUT /me"},
        )
    if body.stage is not None:
        row.stage = body.stage.value
    if body.grade is not None:
        row.grade = body.grade
    if body.subjects is not None:
        row.subjects = [s.value for s in body.subjects]
    db.commit()
    return _build_user_response(db, user.user_id)


# ---------- /me/settings ----------

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
    if body.knowledge_ai_egress_enabled is not None:
        settings.knowledge_ai_egress_enabled = body.knowledge_ai_egress_enabled

    db.commit()
    db.refresh(settings)
    return _serialize_settings(settings)


# ---------- /me/guardian-authorization ----------

# 监护人授权有效期（PRD 8.1：授权需定期续期，默认 1 年）
_GUARDIAN_AUTH_TTL_DAYS = 365


def _gen_confirm_token() -> str:
    """生成监护人确认链接的一次性 token（uuid4 去横线）。"""
    return uuid.uuid4().hex


@router.post(
    "/me/guardian-authorization",
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交监护人联系方式并发送确认请求",
)
def submit_guardian_authorization(
    body: GuardianAuthorizationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """提交监护人联系方式（邮箱/手机二选一），落库 GuardianAuthorization（pending + token）。

    返回 202：确认请求已受理，等待监护人点击链接确认。
    MVP 阶段不真发邮件，token 直接返回（生产环境应发邮件含 confirm 链接）。
    """
    row = db.get(GuardianAuthorizationORM, user.user_id)
    token = _gen_confirm_token()
    if row is None:
        row = GuardianAuthorizationORM(
            user_id=user.user_id,
            guardian_email=body.guardian_email,
            guardian_phone=body.guardian_phone,
            status="pending",
            confirm_token=token,
        )
        db.add(row)
    else:
        row.guardian_email = body.guardian_email
        row.guardian_phone = body.guardian_phone
        row.status = "pending"
        row.confirm_token = token
        row.expires_at = None  # 重新提交时清空之前的过期时间
    db.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete(
    "/me/guardian-authorization",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="撤销监护人授权（账号进入只读）",
)
def revoke_guardian_authorization(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    row = db.get(GuardianAuthorizationORM, user.user_id)
    if row is not None:
        row.status = "revoked"
        row.confirm_token = None
        row.expires_at = None
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/guardian-authorization/confirm",
    summary="监护人点击链接确认授权（无需登录）",
)
def confirm_guardian_authorization(
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """监护人点确认链接：查 token → 置 active + 设置 expires_at。

    token 无效或已使用返回 ok=False。无需登录（security: []）。
    """
    from sqlalchemy import select

    # token 是一次性凭证，查所有 pending 行匹配
    row = db.execute(
        select(GuardianAuthorizationORM).where(
            GuardianAuthorizationORM.confirm_token == token,
            GuardianAuthorizationORM.status == "pending",
        )
    ).scalars().first()

    if row is None:
        return {"ok": False}

    row.status = "active"
    row.expires_at = datetime.utcnow() + timedelta(days=_GUARDIAN_AUTH_TTL_DAYS)
    row.confirm_token = None  # 一次性，确认后清空
    db.commit()
    return {"ok": True}

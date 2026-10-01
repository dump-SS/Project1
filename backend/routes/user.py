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
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import HTMLResponse
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

# ---------- 低龄强制门槛（D41） ----------

# 「未满 14 周岁」的判定口径：只采集出生**年份**（最小必要，不采集精确生日），
# 因此年龄只能算到区间。判定取**保守侧**——宁可多拦一次，也不放走可能未满 14 岁的账号：
#   current_year - birth_year <= 14  → 可能未满 14 周岁 → 需要已生效的监护人授权
#   current_year - birth_year >= 15  → 确定已满 14 周岁 → 不拦
# 例：2012 年出生、2026 年（差 14）→ 拦（可能仍 13 岁）；2011 年出生（差 15）→ 放行。
# 未采集 birth_year 的存量账号（None）不拦截——门槛只对激活式建档采集过的账号生效。
_UNDER14_YEAR_GAP = 14


def _is_under_14(birth_year: int | None, today: date | None = None) -> bool:
    """按出生年份保守判定「可能未满 14 周岁」。"""
    if birth_year is None:
        return False
    today = today or date.today()
    return (today.year - birth_year) <= _UNDER14_YEAR_GAP


def _guardian_status(db: Session, user_id: str) -> str:
    """监护人授权状态；无记录视为 pending（PRD 8.1：未授权视为待确认）。"""
    row = db.get(GuardianAuthorizationORM, user_id)
    return row.status if row is not None else "pending"


def _onboarding_completed(db: Session, user_id: str, birth_year: int | None) -> bool:
    """档案能否置为「已完成」：未满 14 岁时必须监护人授权 active（D41）。"""
    if not _is_under_14(birth_year):
        return True
    return _guardian_status(db, user_id) == "active"


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
            "experienceImprovementEnabled": settings.experience_improvement_enabled,
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
    """幂等建档：用户不存在则创建，存在则覆盖（PUT 语义）。

    低龄强制门槛（D41）：`birthYear` 推算为「可能未满 14 周岁」且监护人授权尚未 `active` 时，
    资料照常落库，但 `onboardingCompleted` 保持 false——前端据此进入监护人授权步骤；
    授权生效后重调本接口即置 true（幂等）。
    """
    existing = db.get(UserORM, user.user_id)
    # birthYear 未传（None）表示"本次不改动"：不覆盖已采集的值，避免误清空
    birth_year = body.birth_year if body.birth_year is not None else (
        existing.birth_year if existing is not None else None
    )
    completed = _onboarding_completed(db, user.user_id, birth_year)

    if existing is None:
        row = UserORM(
            id=user.user_id,
            stage=body.stage.value,
            grade=body.grade,
            subjects=[s.value for s in body.subjects],
            birth_year=birth_year,
            onboarding_completed=completed,
        )
        db.add(row)
    else:
        row = existing
        row.stage = body.stage.value
        row.grade = body.grade
        row.subjects = [s.value for s in body.subjects]
        row.birth_year = birth_year
        row.onboarding_completed = completed
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
    if body.birth_year is not None:
        row.birth_year = body.birth_year
    # 改动 birthYear 后重算门槛：改成未满 14 岁且授权未生效 → 档案回到「未完成」，
    # 前端会重新把用户带回监护人授权步骤（D41 是强制门槛，不是一次性检查）。
    row.onboarding_completed = _onboarding_completed(db, user.user_id, row.birth_year)
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
    if body.experience_improvement_enabled is not None:
        settings.experience_improvement_enabled = body.experience_improvement_enabled

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
    # MVP 演示期：不真发邮件，把 token 直接返回前端拼接确认链接；
    # 生产上线前必须改为 SMTP 真发邮件（见 B6），并移除这里的 token 返回。
    return {"confirmToken": token}


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
        # 低龄门槛重算（D41）：撤销后未满 14 岁的账号回到「未完成建档」，
        # 前端会把用户带回监护人授权步骤；≥14 岁账号不受影响。
        user_row = db.get(UserORM, user.user_id)
        if user_row is not None:
            user_row.onboarding_completed = _onboarding_completed(
                db, user.user_id, user_row.birth_year
            )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/guardian-authorization/confirm",
    summary="监护人点击链接确认授权（无需登录）",
)
def confirm_guardian_authorization(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """监护人点确认链接：查 token → 置 active + 设置 expires_at。

    token 无效或已使用返回 ok=False。无需登录（security: []）。

    **结果页**：监护人是从邮件里点开链接的——他既没有账号、也不在应用内，
    所以 `Accept` 首选 `text/html`（浏览器地址栏/邮件客户端直开）时返回自包含 HTML 结果页，
    不依赖前端构建产物；接口客户端（前端 fetch、自动化测试）仍拿 `{"ok": bool}`，语义不变。
    """
    from sqlalchemy import select

    # token 是一次性凭证，查所有 pending 行匹配
    row = db.execute(
        select(GuardianAuthorizationORM).where(
            GuardianAuthorizationORM.confirm_token == token,
            GuardianAuthorizationORM.status == "pending",
        )
    ).scalars().first()

    ok = row is not None
    if ok:
        row.status = "active"
        row.expires_at = datetime.utcnow() + timedelta(days=_GUARDIAN_AUTH_TTL_DAYS)
        row.confirm_token = None  # 一次性，确认后清空
        db.commit()

    if _wants_html(request):
        return HTMLResponse(_guardian_result_page(ok))
    return {"ok": ok}


# ---------- 监护人确认结果页（自包含 HTML） ----------

def _wants_html(request: Request) -> bool:
    """Accept 首选 text/html → 浏览器/邮件客户端直开；其余（*/*、application/json）走 JSON。"""
    accept = request.headers.get("accept", "")
    return accept.split(",")[0].strip().lower().startswith("text/html")


def _guardian_result_page(ok: bool) -> str:
    """监护人人看到的结果页。

    监护人不装 App、不登录，页面必须**自包含**（内联样式、无 JS、无外部资源），
    并明确说清三件事：这次确认的结果、授权的有效期、以及在哪里可以撤销。
    """
    if ok:
        icon, title, tone = "✓", "授权已确认", "#0E9F6E"
        body = (
            "<p class=\"line\">你已确认对该账号的监护人授权，账号可以正常使用了。</p>"
            "<ul class=\"facts\">"
            "<li>授权有效期 <strong>12 个月</strong>，到期后需重新确认。</li>"
            "<li>你可以随时撤销：账号持有人可在「设置 → 授权与隐私」内查看状态并撤销；"
            "撤销后该账号将进入只读状态。</li>"
            "<li>如果你并不认识这个账号，或并未同意，请忽略本页，并通过下方邮箱联系我们。</li>"
            "</ul>"
        )
    else:
        icon, title, tone = "!", "链接无效或已使用", "#B45309"
        body = (
            "<p class=\"line\">这个确认链接不存在、已经使用过，或已被重新发起而失效。</p>"
            "<ul class=\"facts\">"
            "<li>如果授权此前已经确认过，你无需再做任何操作。</li>"
            "<li>如果需要重新确认，请让账号持有人重新提交监护人联系方式，你会收到新的确认链接。</li>"
            "</ul>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>EpochX · 监护人授权确认</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    padding: 24px; background: #F5F7FA; color: #1F2937;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  }}
  .card {{
    width: 100%; max-width: 520px; background: #FFFFFF; border-radius: 16px;
    padding: 32px 28px; box-shadow: 0 8px 30px rgba(16, 22, 30, 0.08);
  }}
  .badge {{
    width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-size: 22px; font-weight: 700; color: #FFFFFF;
    background: {tone}; margin-bottom: 16px;
  }}
  h1 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.4; }}
  .brand {{ margin: 0 0 20px; font-size: 13px; color: #6B7280; letter-spacing: .04em; }}
  .line {{ margin: 0 0 12px; font-size: 15px; line-height: 1.7; }}
  .facts {{ margin: 0 0 4px; padding-left: 20px; font-size: 14px; line-height: 1.8; color: #374151; }}
  .facts li {{ margin-bottom: 4px; }}
  footer {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid #E5E7EB; font-size: 12px; color: #9CA3AF; line-height: 1.7; }}
  a {{ color: #2563EB; text-decoration: none; }}
</style>
</head>
<body>
  <main class="card">
    <div class="badge" aria-hidden="true">{icon}</div>
    <h1>{title}</h1>
    <p class="brand">EpochX · 监护人授权</p>
    {body}
    <footer>
      EpochX 由学生团队开发，目前处于 pilot 封测阶段，本页文案未经专业法律审核。<br />
      如需协助，请通过监护人联系邮箱与我们联系，或返回 <a href="/">EpochX 首页</a>。
    </footer>
  </main>
</body>
</html>"""
    row.confirm_token = None  # 一次性，确认后清空
    db.commit()
    return {"ok": True}

"""/auth/* 系列接口（从 mock-server 迁移）。

10 个接口，路径/请求体/响应体/Cookie 行为与 mock-server 完全一致：
1. POST /auth/send-register-code
2. POST /auth/send-reset-code
3. POST /auth/send-login-code
4. POST /auth/register
5. POST /auth/login-email-code
6. POST /auth/login-password
7. GET  /auth/me
8. POST /auth/logout
9. POST /auth/verify-reset-code
10. POST /auth/reset-password

迁移后 Python 后端统一处理 auth + 业务，mock-server 可退役。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.code import consume_code, store_code, verify_code
from auth.email import send_code_email
from auth.models import AuthUser
from auth.password import hash_password, is_strong_password, verify_password
from auth.rate_limit import allow, clear_fails, is_locked, record_fail
from auth.session import COOKIE_NAME, create_session, destroy_all_sessions_for_user, destroy_session, get_session
from database import get_db
from models.user import User as UserORM

router = APIRouter(prefix="/auth", tags=["鉴权会话"])

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def generate_user_id() -> str:
    """生成稳定用户 ID（D59）：`u_` 前缀 + 16 位 hex 短码。

    保持 `u_` 前缀是为了兼容既有测试与调试通道（8 个测试文件用 `X-User-ID: u_xxx`）。
    16 hex = 64 bit 随机空间，pilot 量级下碰撞概率可忽略。
    """
    return "u_" + uuid.uuid4().hex[:16]


def _ensure_stable_user_id(db: Session, auth_user: AuthUser) -> str:
    """取认证行关联的稳定 user_id；缺失时补齐。

    正常注册流程已在注册时就写好 user_id，这里是兜底路径（历史行 / 测试直接造的
    AuthUser）：生成 ID → 建业务 users 行（带 email）→ 回写 auth_users.user_id。
    """
    if auth_user.user_id:
        return auth_user.user_id

    user_id = generate_user_id()
    if db.get(UserORM, user_id) is None:
        db.add(UserORM(
            id=user_id,
            email=auth_user.email,
            stage="senior",  # 建档前的占位值，与 deps 的桩保持一致
            grade="",
            subjects=["other"],
            onboarding_completed=False,
        ))
    auth_user.user_id = user_id
    db.commit()
    return user_id


# ---------- 请求体 schemas ----------

class EmailRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    code: str
    password: str
    confirmPassword: str


class LoginCodeRequest(BaseModel):
    email: str
    code: str


class LoginPasswordRequest(BaseModel):
    email: str
    password: str


class VerifyResetCodeRequest(BaseModel):
    email: str
    code: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    newPassword: str
    confirmPassword: str


# ---------- 1-3. 发送验证码 ----------

def _send_code(code_type: str, email: str, db: Session, check_registered: bool | None = None) -> dict:
    """发送验证码的共用逻辑。

    check_registered: True=要求已注册(login/reset)，False=要求未注册(register)，None=不检查。
    """
    if not EMAIL_RE.match(email):
        raise _validation_error("邮箱格式不正确", "email")

    existing = db.get(AuthUser, email)
    if check_registered is True and not existing:
        raise _error(404, "EMAIL_NOT_REGISTERED", "该邮箱尚未注册，请先注册", "email")
    if check_registered is False and existing:
        raise _error(409, "EMAIL_ALREADY_REGISTERED", "该邮箱已注册，请直接登录", "email")

    if not allow("code:" + email, 1, 60_000):
        raise _error(429, "RATE_LIMITED", "验证码发送过于频繁，请稍后再试")

    code = store_code(db, code_type, email)
    try:
        send_code_email(code_type, email, code)
    except Exception:
        # SMTP 失败不阻断——验证码已存 DB，开发环境可通过日志拿到
        import logging
        logging.getLogger(__name__).exception("[SMTP] 发送 %s 验证码失败: %s", code_type, email)

    return {"ok": True, "sent": True}


@router.post("/send-register-code", summary="发送注册验证码")
def send_register_code(body: EmailRequest, db: Session = Depends(get_db)):
    return _send_code("register", body.email, db, check_registered=False)


@router.post("/send-reset-code", summary="发送重置密码验证码")
def send_reset_code(body: EmailRequest, db: Session = Depends(get_db)):
    return _send_code("reset", body.email, db, check_registered=True)


@router.post("/send-login-code", summary="发送登录验证码")
def send_login_code(body: EmailRequest, db: Session = Depends(get_db)):
    return _send_code("login", body.email, db, check_registered=True)


# ---------- 4. 注册 ----------

@router.post("/register", status_code=status.HTTP_201_CREATED, summary="注册")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email):
        raise _validation_error("邮箱格式不正确", "email")
    if db.get(AuthUser, body.email):
        raise _error(409, "EMAIL_ALREADY_REGISTERED", "该邮箱已注册，请直接登录", "email")
    if not re.match(r"^\d{6}$", body.code):
        raise _validation_error("验证码为 6 位数字", "code")
    if not body.password or not (6 <= len(body.password) <= 32):
        raise _validation_error("密码长度 6-32 位", "password")
    if not is_strong_password(body.password):
        raise _validation_error("密码需包含大写字母、小写字母、数字、符号中的至少两种", "password")
    if body.password != body.confirmPassword:
        raise _validation_error("两次输入的密码不一致", "confirmPassword")

    if is_locked(body.email):
        raise _error(429, "RATE_LIMITED", "验证失败次数过多，请 15 分钟后再试")

    ok, msg = verify_code(db, "register", body.email, body.code)
    if not ok:
        record_fail(body.email)
        raise _error(400, "CODE_INVALID", msg, "code")
    consume_code(db, "register", body.email)
    clear_fails(body.email)

    # 稳定 ID 改造（D59）改序：先生成稳定 user_id → 建业务 users 行 → 建认证行。
    # 业务 users 行的 id 从此与邮箱解耦：改邮箱只动 email 列，历史数据全部保留。
    # 占位字段与 deps._build_user_response 的未建档桩一致，onboarding_completed=false
    # 让前端继续引导去建档页（PUT /me 会覆盖这些占位值）。
    existing_profile = db.execute(
        select(UserORM).where(UserORM.email == body.email)
    ).scalars().first()
    user_id = existing_profile.id if existing_profile else generate_user_id()

    if existing_profile is None:
        db.add(UserORM(
            id=user_id,
            email=body.email,
            stage="senior",
            grade="",
            subjects=["other"],
            onboarding_completed=False,
        ))
    db.add(AuthUser(
        email=body.email,
        user_id=user_id,
        password_hash=hash_password(body.password),
    ))
    db.commit()
    return {"ok": True}


# ---------- 5-6. 登录 ----------

@router.post("/login-email-code", summary="邮箱+验证码登录")
def login_email_code(body: LoginCodeRequest, response: Response, db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email):
        raise _validation_error("邮箱格式不正确", "email")
    auth_user = db.get(AuthUser, body.email)
    if not auth_user:
        raise _error(404, "EMAIL_NOT_REGISTERED", "该邮箱尚未注册，请先注册", "email")

    if is_locked(body.email):
        raise _error(429, "RATE_LIMITED", "验证失败次数过多，请 15 分钟后再试")

    ok, msg = verify_code(db, "login", body.email, body.code)
    if not ok:
        record_fail(body.email)
        raise _error(400, "CODE_INVALID", msg, "code")
    consume_code(db, "login", body.email)
    clear_fails(body.email)

    # 会话存稳定 user_id（D59），不存邮箱
    _, cookie = create_session(db, _ensure_stable_user_id(db, auth_user))
    response.headers["Set-Cookie"] = cookie
    return {"ok": True}


@router.post("/login-password", summary="邮箱+密码登录")
def login_password(body: LoginPasswordRequest, response: Response, db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email):
        raise _validation_error("邮箱格式不正确", "email")
    if not body.password:
        raise _validation_error("请输入密码", "password")

    user = db.get(AuthUser, body.email)
    if not user:
        raise _error(404, "EMAIL_NOT_REGISTERED", "该邮箱尚未注册，请先注册", "email")

    if is_locked(body.email):
        raise _error(429, "RATE_LIMITED", "验证失败次数过多，请 15 分钟后再试")

    if not verify_password(body.password, user.password_hash):
        record_fail(body.email)
        raise _error(401, "PASSWORD_INCORRECT", "密码错误", "password")
    clear_fails(body.email)

    _, cookie = create_session(db, _ensure_stable_user_id(db, user))
    response.headers["Set-Cookie"] = cookie
    return {"ok": True}


# ---------- 7-8. 会话 ----------

@router.get("/me", summary="获取当前登录用户")
def auth_me(sid: str | None = Cookie(default=None, alias=COOKIE_NAME), db: Session = Depends(get_db)):
    """返回当前会话对应的邮箱与稳定 userId。

    session 存的是 user_id（D59），邮箱从 auth_users 反查——它是登录凭证、可改，
    所以不作为身份下发依据，只作展示与前端兼容（AppShell 显示 email）。
    """
    user_id = get_session(db, sid)
    if not user_id:
        raise _error(401, "UNAUTHORIZED", "未登录或登录已过期")

    auth_user = db.execute(
        select(AuthUser).where(AuthUser.user_id == user_id)
    ).scalars().first()
    if auth_user is None:
        # 会话指向的认证账号已不存在（注销/换绑遗留）——按未登录处理，不暴露半截状态
        raise _error(401, "UNAUTHORIZED", "登录状态已失效，请重新登录")

    return {"ok": True, "user": {"email": auth_user.email, "userId": user_id}}


@router.post("/logout", summary="退出登录")
def auth_logout(response: Response, sid: str | None = Cookie(default=None, alias=COOKIE_NAME), db: Session = Depends(get_db)):
    cookie = destroy_session(db, sid)
    response.headers["Set-Cookie"] = cookie
    return {"ok": True}


# ---------- 9-10. 重置密码 ----------

@router.post("/verify-reset-code", summary="校验重置验证码（不消费）")
def verify_reset_code(body: VerifyResetCodeRequest, db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email):
        raise _validation_error("邮箱格式不正确", "email")

    if is_locked(body.email):
        raise _error(429, "RATE_LIMITED", "验证失败次数过多，请 15 分钟后再试")

    ok, msg = verify_code(db, "reset", body.email, body.code)
    if not ok:
        record_fail(body.email)
        raise _error(400, "CODE_INVALID", msg, "code")
    # 不消费——reset-password 还会再校验一次
    return {"ok": True}


@router.post("/reset-password", summary="重置密码")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email):
        raise _validation_error("邮箱格式不正确", "email")
    if not re.match(r"^\d{6}$", body.code):
        raise _validation_error("验证码为 6 位数字", "code")
    if not body.newPassword or not (6 <= len(body.newPassword) <= 32):
        raise _validation_error("密码长度 6-32 位", "newPassword")
    if not is_strong_password(body.newPassword):
        raise _validation_error("密码需包含大写字母、小写字母、数字、符号中的至少两种", "newPassword")
    if body.newPassword != body.confirmPassword:
        raise _validation_error("两次输入的密码不一致", "confirmPassword")

    user = db.get(AuthUser, body.email)
    if not user:
        raise _error(404, "EMAIL_NOT_REGISTERED", "该邮箱尚未注册，请先注册", "email")

    if is_locked(body.email):
        raise _error(429, "RATE_LIMITED", "验证失败次数过多，请 15 分钟后再试")

    ok, msg = verify_code(db, "reset", body.email, body.code)
    if not ok:
        record_fail(body.email)
        raise _error(400, "CODE_INVALID", msg, "code")
    consume_code(db, "reset", body.email)
    clear_fails(body.email)

    user.password_hash = hash_password(body.newPassword)
    db.commit()
    # 密码已改，使该用户所有已有会话失效（按稳定 user_id 清——改过邮箱也清得干净）
    destroy_all_sessions_for_user(db, _ensure_stable_user_id(db, user))
    return {"ok": True}


# ---------- 错误工具 ----------

def _validation_error(message: str, field: str):
    from fastapi import HTTPException
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "VALIDATION_FAILED", "message": message, "field": field},
    )


def _error(status_code: int, code: str, message: str, field: str | None = None):
    from fastapi import HTTPException
    detail = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=status_code, detail=detail)

"""稳定用户 ID（D59）回归测试 —— 对应重构 M0 的验收门。

覆盖：
1. 注册即生成稳定 `u_` 短码，业务 users 行与认证行同时建立并互相指向；
2. **改邮箱后 users.id 不变、业务数据全部保留**（改造前 id 里填的是邮箱，
   改邮箱 = 换主键 = 全表外键更新）；
3. 会话存的是 user_id 而不是 email，改邮箱不会让已有会话串号；
4. /auth/me 同时下发 email（展示用）与 userId（身份用）。

⚠️ 全仓目前**没有「改邮箱」接口**（契约 /auth/* 只有 10 条）——该接口归 A 板块。
所以第 2 条用例在 ORM 层模拟 A 板块将来要做的写序（只改 email 两列），
验证数据模型本身支持这件事；接口落地后应补一条端到端用例。
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from auth.models import AuthUser
from auth.password import hash_password
from auth.session import create_session
from database import SessionLocal
from main import app
from models.goal import Goal
from models.user import User as UserORM
from routes.auth import generate_user_id

client = TestClient(app)

PASSWORD = "Aa1!aaaa"


def _register_via_api(monkeypatch, email: str) -> None:
    """走真实注册接口建号（验证码环节打桩，避免依赖邮件与 SHA256 反推）。"""
    monkeypatch.setattr("routes.auth.verify_code", lambda *a, **k: (True, ""))
    monkeypatch.setattr("routes.auth.consume_code", lambda *a, **k: None)

    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "code": "123456",
            "password": PASSWORD,
            "confirmPassword": PASSWORD,
        },
    )
    assert r.status_code == 201, r.text


def test_register_creates_stable_id_and_linked_rows(monkeypatch):
    """注册后：users.id 是 u_ 短码（不是邮箱），且 auth_users.user_id 指向它。"""
    email = "stable_id_register@example.com"
    _register_via_api(monkeypatch, email)

    db = SessionLocal()
    try:
        auth_user = db.get(AuthUser, email)
        assert auth_user is not None, "注册应写入 auth_users 行"
        assert auth_user.user_id, "auth_users.user_id 必须被填上"
        assert auth_user.user_id.startswith("u_"), "稳定 ID 保持 u_ 前缀（测试与调试通道兼容）"
        assert auth_user.user_id != email, "稳定 ID 不能是邮箱"

        user_row = db.get(UserORM, auth_user.user_id)
        assert user_row is not None, "注册应同时建好业务 users 行（D59 改序）"
        assert user_row.email == email
        # 建档前应为未完成态，前端据此引导去建档页
        assert user_row.onboarding_completed is False
    finally:
        db.close()


def test_email_change_keeps_user_id_and_data(monkeypatch):
    """改邮箱 → users.id 不变、业务数据全保留、新邮箱仍能登进同一个账号。

    这是 D59 的核心验收：改造前 users.id 填的就是邮箱，改邮箱等于换主键。
    """
    old_email = "before_change@example.com"
    new_email = "after_change@example.com"
    _register_via_api(monkeypatch, old_email)

    db = SessionLocal()
    try:
        auth_user = db.get(AuthUser, old_email)
        user_id = auth_user.user_id

        # 造一条业务数据（挂在该 user_id 上），模拟用户已有学习数据
        db.add(Goal(
            id="g_stable_id_test",
            user_id=user_id,
            type="short_term",
            subject="SX",
            title="改邮箱前建的目标",
            status="active",
            planned_tasks=0,
            completed_tasks=0,
        ))
        db.commit()

        # 模拟 A 板块将来的「改邮箱」写序：只改两处 email，users.id 一律不动
        db.execute(update(AuthUser).where(AuthUser.user_id == user_id).values(email=new_email))
        user_row = db.get(UserORM, user_id)
        user_row.email = new_email
        db.commit()

        # 1) 主键不变
        assert db.get(UserORM, user_id) is not None, "users.id 必须保持不变"
        assert db.get(UserORM, new_email) is None, "不允许出现以邮箱为主键的用户行"
        # 2) 业务数据保留，且仍挂同一个 user_id
        goal = db.get(Goal, "g_stable_id_test")
        assert goal is not None, "改邮箱后业务数据必须全部保留"
        assert goal.user_id == user_id
        # 3) 认证行按新邮箱可查，且指向同一稳定 ID
        moved = db.execute(
            select(AuthUser).where(AuthUser.email == new_email)
        ).scalars().first()
        assert moved is not None and moved.user_id == user_id
        # 旧邮箱不应再有认证行（用 select 而不是 db.get：后者会命中 identity map 缓存，
        # 返回的是同一个已被改过 email 的对象，断言会失真）
        assert db.execute(
            select(AuthUser).where(AuthUser.email == old_email)
        ).scalars().first() is None
    finally:
        db.close()

    # 4) 用新邮箱 + 原密码登录，拿到的仍是同一个稳定 userId
    r = client.post(
        "/api/v1/auth/login-password",
        json={"email": new_email, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()["user"]
    assert body["email"] == new_email, "展示用邮箱应更新为新邮箱"
    assert body["userId"].startswith("u_"), "身份用 ID 应是稳定短码"


def test_session_survives_email_change(monkeypatch):
    """会话存 user_id：改邮箱后原会话依然有效（不会因改邮箱被踢或串号）。"""
    old_email = "session_before@example.com"
    new_email = "session_after@example.com"

    db = SessionLocal()
    try:
        user_id = generate_user_id()
        db.add(UserORM(
            id=user_id, email=old_email, stage="senior", grade="",
            subjects=["other"], onboarding_completed=False,
        ))
        db.add(AuthUser(email=old_email, user_id=user_id, password_hash=hash_password(PASSWORD)))
        db.commit()
        sid, _ = create_session(db, user_id)

        # 改邮箱（同样只动 email 两列）
        db.execute(update(AuthUser).where(AuthUser.user_id == user_id).values(email=new_email))
        db.get(UserORM, user_id).email = new_email
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/auth/me", cookies={"sid": sid})
    assert r.status_code == 200, "改邮箱不应使已有会话失效"
    assert r.json()["user"]["userId"] == user_id
    assert r.json()["user"]["email"] == new_email

"""鉴权严格模式回归测试：生产口径下「无有效会话 → 401」。

背景：`routes/deps.py:current_user` 原有一条四层身份回落链，其中第 2 层
（X-User-ID 头）、第 3 层（Bearer u_ 前缀 token）允许请求方自报身份，第 4 层
无会话时兜底共享账号 u_10237——任何人不带 cookie 就能读写任意用户数据。

现在这四层统一由 `config.settings.allow_insecure_user_header` 控制：
- false（生产默认）：身份唯一来源是 sid cookie，无有效会话一律 401
- true（仅测试/联调）：回落链启用，行为与改造前一致（见 tests/conftest.py）

本文件把开关切到 false 验证生产口径；最后一条用例验证开关打开时回落链
仍然生效，防止测试环境被误伤。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from auth.models import AuthUser
from auth.password import hash_password
from auth.session import create_session
from config import settings
from database import SessionLocal
from main import app
from models.user import User as UserORM
from routes.auth import generate_user_id

client = TestClient(app)


def _login(email: str) -> tuple[str, str]:
    """造一条完整的「业务行 + 认证行 + 会话」链路，返回 (raw_sid, user_id)。

    走的是注册流程同一套写序（D59：先生成稳定 user_id → 建 users 行 → 建 AuthUser 行），
    只是跳过了邮件验证码环节。

    ⚠️ 返回的 user_id 与传入的 email 是**两个不同的值**——这正是稳定 ID 改造的要点：
    会话与业务数据挂在 user_id 上，email 只是可改的登录凭证。
    """
    db = SessionLocal()
    try:
        user_id = generate_user_id()
        db.add(UserORM(
            id=user_id,
            email=email,
            stage="senior",
            grade="",
            subjects=["other"],
            onboarding_completed=False,
        ))
        db.add(AuthUser(
            email=email,
            user_id=user_id,
            password_hash=hash_password("Aa1!aaaa"),
        ))
        db.commit()
        raw_sid, _cookie = create_session(db, user_id)
        return raw_sid, user_id
    finally:
        db.close()


# ---------- 生产口径（allow_insecure_user_header=false）----------

def test_no_cookie_business_call_returns_401(monkeypatch):
    """无 cookie 访问业务接口 → 401 UNAUTHENTICATED（不再兜底 u_10237）。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"

    r = client.get("/api/v1/goals")
    assert r.status_code == 401


def test_x_user_id_header_is_ignored_when_disabled(monkeypatch):
    """生产配置下 X-User-ID 头不再被采信（原垂直越权入口）。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    r = client.get("/api/v1/me", headers={"X-User-ID": "u_10238"})
    assert r.status_code == 401, "X-User-ID 自报身份必须被拒绝"


def test_bearer_u_token_is_ignored_when_disabled(monkeypatch):
    """生产配置下 Bearer u_ 前缀 token 不再被采信（原垂直越权入口）。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    r = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer u_10238"},
    )
    assert r.status_code == 401, "Bearer u_ 自报身份必须被拒绝"


def test_invalid_sid_returns_401(monkeypatch):
    """sid 无效（查不到会话）→ 401，而不是回落成匿名用户。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    r = client.get("/api/v1/me", cookies={"sid": "0" * 64})
    assert r.status_code == 401


def test_valid_sid_cookie_returns_that_user(monkeypatch):
    """有效 sid cookie → 200，且返回该会话对应的用户（第 1 层保持不变）。

    D59 后 userId 是稳定短码，与邮箱解耦：这里显式断言两者不同，
    防止将来有人把 userId 又改回邮箱（那会让改邮箱变成换主键）。
    """
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    email = "strict_mode_user@example.com"
    sid, user_id = _login(email)

    r = client.get("/api/v1/me", cookies={"sid": sid})
    assert r.status_code == 200
    assert r.json()["userId"] == user_id
    assert r.json()["userId"] != email, "userId 必须是稳定 ID，不是邮箱"

    # 无 cookie 时同一请求应 401——确认上面的 200 确实来自会话而非兜底
    assert client.get("/api/v1/me").status_code == 401


def test_sid_takes_precedence_over_x_user_id(monkeypatch):
    """有效 sid 优先于 X-User-ID：即使带上冒充头也返回会话本人。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", True)

    email = "strict_mode_owner@example.com"
    sid, user_id = _login(email)

    r = client.get(
        "/api/v1/me",
        cookies={"sid": sid},
        headers={"X-User-ID": "u_someone_else"},
    )
    assert r.status_code == 200
    assert r.json()["userId"] == user_id


# ---------- 测试环境口径（allow_insecure_user_header=true）----------

def test_insecure_chain_still_works_when_enabled(monkeypatch):
    """开关打开时回落链照旧生效，保证既有测试用例行为不变。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", True)

    r = client.get("/api/v1/me", headers={"X-User-ID": "u_insecure_ok"})
    assert r.status_code == 200
    assert r.json()["userId"] == "u_insecure_ok"

    r = client.get("/api/v1/me", headers={"Authorization": "Bearer u_bearer_ok"})
    assert r.status_code == 200
    assert r.json()["userId"] == "u_bearer_ok"

    # 无任何身份信息 → 匿名兜底 u_10237（仅测试环境）
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    assert r.json()["userId"] == "u_10237"


def test_conftest_enables_insecure_chain_by_default():
    """测试套件默认走宽松模式（conftest.py 设的 env），否则大量既有用例会 401。"""
    assert settings.allow_insecure_user_header is True

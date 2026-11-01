"""X2 权限测试：把散落在各测试文件里的 401 / 403 / 越权断言收拢成一套。

三组口径（全部按**当前实现的真实行为**断言，并在组头写明口径依据）：

1. **未登录 → 401**（生产口径，`allow_insecure_user_header=false`）：
   身份唯一来源是 sid cookie；无 cookie 访问任何受保护接口一律 401
   UNAUTHENTICATED。回落链行为（X-User-ID 头 / Bearer u_ / 匿名兜底）由
   `tests/test_auth_strict_mode.py` 专测，这里不重复。
2. **越权 → 403**（明确「无权」语义的接口）：
   `/f/media/*` 与 `/chat/jobs/{jobId}` 的归属校验**故意用 403 而非 404**——
   语义是「你无权访问」，且**不泄露资源是否存在**；路径穿越同样 403。
   依据：routes/f_media.py `_assert_owner` 与 routes/chat.py get_chat_job 注释。
3. **跨用户资源 → 404**（防枚举口径）：
   goal / plan / timer / error-book / learning-record / summary /
   recommendation / exam 的行级归属校验统一返回 404 RESOURCE_NOT_FOUND
   （`row.user_id != 当前用户` 即当作不存在），与 403 组形成有意对比。

⚠️ 本文件是**收拢**不是搬家：原 403 断言（test_f_media.py /
test_chat_async.py 等）保留不动，避免删别人领地里的测试。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from auth.models import AuthUser
from auth.password import hash_password
from auth.session import create_session
from config import settings
from database import SessionLocal
from main import app
from models.chat import ChatJob
from models.user import User as UserORM
from routes.auth import generate_user_id

client = TestClient(app)


def _make_login(tag: str) -> tuple[str, str]:
    """造一条「users 行 + AuthUser 行 + 会话」链路，返回 (raw_sid, user_id)。"""
    suffix = uuid.uuid4().hex[:8]
    email = f"x2-perm-{tag}-{suffix}@test.local"
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


def _cookie(sid: str) -> dict[str, str]:
    return {"Cookie": f"sid={sid}"}


# ---------- 组 1：未登录 → 401（生产口径） ----------


def test_no_cookie_gets_401_across_protected_endpoints(monkeypatch):
    """无 cookie 打代表性受保护接口 → 全部 401 UNAUTHENTICATED。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", False)

    cases: list[tuple[str, str, dict | None]] = [
        ("GET", "/api/v1/me", None),
        ("GET", "/api/v1/goals", None),
        ("GET", "/api/v1/me/usage", None),
        ("POST", "/api/v1/chat", {"content": "在吗"}),
        ("POST", "/api/v1/learning-records", {}),
        ("GET", "/api/v1/f/media/user/u_x/1.png", None),
        ("GET", "/api/v1/chat/jobs/cj_nonexistent", None),
        ("GET", "/api/v1/knowledge/subjects", None),
    ]
    for method, url, body in cases:
        r = client.request(method, url, json=body)
        assert r.status_code == 401, f"{method} {url} → {r.status_code}, 期望 401"
        assert r.json()["error"]["code"] == "UNAUTHENTICATED", f"{method} {url} 错误码不符"


# ---------- 组 2：越权 → 403（/f/media 与 /chat/jobs 的显式语义） ----------


def test_media_of_other_user_is_403_on_get_and_delete():
    """别人的媒体 key：GET / DELETE 都是 403，而不是 404（不泄露存在性）。"""
    sid_a, uid_a = _make_login("media-a")
    _sid_b, uid_b = _make_login("media-b")

    other_key = f"user/{uid_b}/e2e-not-really-there.png"
    r = client.get(f"/api/v1/f/media/{other_key}", headers=_cookie(sid_a))
    assert r.status_code == 403, f"GET 他人 key → {r.status_code}，期望 403"
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.delete(f"/api/v1/f/media/{other_key}", headers=_cookie(sid_a))
    assert r.status_code == 403, f"DELETE 他人 key → {r.status_code}，期望 403"

    # 自己前缀的 key 才放行进入取物阶段（R2 未配置 → 503，而非 403）：
    own_key = f"user/{uid_a}/e2e-not-really-there.png"
    r = client.get(f"/api/v1/f/media/{own_key}", headers=_cookie(sid_a))
    assert r.status_code == 503, f"自己的 key（R2 未配置）→ {r.status_code}，期望 503"
    assert r.json()["error"]["code"] == "R2_NOT_CONFIGURED"


def test_media_path_traversal_is_403():
    """路径穿越（`../`）一律 403，不进入 R2。"""
    sid, _uid = _make_login("traverse")
    for bad in ("user/../secret.png", "user/%2e%2e/secret.png", "user/{uuid}/../other.png"):
        r = client.get(f"/api/v1/f/media/{bad}", headers=_cookie(sid))
        assert r.status_code == 403, f"穿越 key {bad!r} → {r.status_code}，期望 403"


def test_chat_job_of_other_user_is_403():
    """他人的带图任务：403（不是 404）——语义是「无权访问」。"""
    sid_a, _uid_a = _make_login("job-a")
    _sid_b, uid_b = _make_login("job-b")

    db = SessionLocal()
    try:
        job = ChatJob(
            id=f"cj_perm_{uuid.uuid4().hex[:10]}",
            user_id=uid_b,
            status="done",
            content="越权探针",
            media_key=f"user/{uid_b}/x.png",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    r = client.get(f"/api/v1/chat/jobs/{job_id}", headers=_cookie(sid_a))
    assert r.status_code == 403, f"他人 jobId → {r.status_code}，期望 403"
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_chat_with_media_key_of_other_user_is_403():
    """同步 /chat 带**他人** mediaKey → 403（归属校验先于 R2 取图）。"""
    sid_a, _uid_a = _make_login("chat-a")
    _sid_b, uid_b = _make_login("chat-b")

    r = client.post(
        "/api/v1/chat",
        json={"content": "看这张图", "mediaKey": f"user/{uid_b}/nope.png"},
        headers=_cookie(sid_a),
    )
    assert r.status_code == 403, f"同步 /chat 他人 mediaKey → {r.status_code}，期望 403"

    r = client.post(
        "/api/v1/chat/media",
        json={"content": "看这张图", "mediaKey": f"user/{uid_b}/nope.png"},
        headers=_cookie(sid_a),
    )
    assert r.status_code == 403, f"/chat/media 他人 mediaKey → {r.status_code}，期望 403"


# ---------- 组 3：跨用户资源 → 404（防枚举口径） ----------


def test_cross_user_goal_is_404():
    """他人目标：404 RESOURCE_NOT_FOUND（不是 403）——防止按 id 枚举。"""
    sid_a, uid_a = _make_login("goal-a")
    sid_b, _uid_b = _make_login("goal-b")

    r = client.post(
        "/api/v1/goals",
        json={"type": "short_term", "subject": "SX", "title": "A 的目标"},
        headers=_cookie(sid_a),
    )
    assert r.status_code == 201, f"建目标失败：{r.status_code} {r.text[:200]}"
    goal_id = r.json()["goalId"] or r.json()["id"]

    r = client.get(f"/api/v1/goals/{goal_id}", headers=_cookie(sid_b))
    assert r.status_code == 404, f"B 读 A 的目标 → {r.status_code}，期望 404"
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    r = client.patch(
        f"/api/v1/goals/{goal_id}",
        json={"title": "B 改 A 的目标"},
        headers=_cookie(sid_b),
    )
    assert r.status_code == 404, f"B 改 A 的目标 → {r.status_code}，期望 404"

    # 属主仍可读（对照组：不是「接口坏了」）
    r = client.get(f"/api/v1/goals/{goal_id}", headers=_cookie(sid_a))
    assert r.status_code == 200, f"属主读自己的目标 → {r.status_code}，期望 200"


def test_cross_user_learning_record_is_404():
    sid_a, _uid_a = _make_login("rec-a")
    sid_b, _uid_b = _make_login("rec-b")

    r = client.post(
        "/api/v1/learning-records",
        json={
            "subject": "SX",
            "startedAt": "2026-10-30T10:00:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed"},
        },
        headers=_cookie(sid_a),
    )
    assert r.status_code == 201, f"建记录失败：{r.status_code} {r.text[:200]}"
    rec_id = r.json()["recordId"]

    # ⚠️ 学习记录没有 GET-by-id 路由（GET 会被 SPA catch-all 吞成
    # FRONTEND_NOT_DEPLOYED 404，语义完全不同）；带归属校验的是 DELETE。
    r = client.delete(f"/api/v1/learning-records/{rec_id}", headers=_cookie(sid_b))
    assert r.status_code == 404, f"B 删 A 的记录 → {r.status_code}，期望 404"
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # 属主的数据仍在：列表里还能看到这条记录（对照组）
    r = client.get("/api/v1/learning-records?page=1&pageSize=50", headers=_cookie(sid_a))
    assert r.status_code == 200
    ids = [item.get("recordId") for item in r.json().get("items", [])]
    assert rec_id in ids, "属主的记录不该被他人删掉"


def test_cross_user_error_book_item_is_404():
    sid_a, _uid_a = _make_login("eb-a")
    sid_b, _uid_b = _make_login("eb-b")

    r = client.post(
        "/api/v1/error-book",
        json={"subject": "SX", "rawText": "1+1=3 错在哪"},
        headers=_cookie(sid_a),
    )
    assert r.status_code in (200, 201), f"建错题失败：{r.status_code} {r.text[:200]}"
    d = r.json()
    item_id = d.get("errorId") or d.get("id") or (d.get("error") or {}).get("id")
    assert item_id, f"响应里拿不到错题 id：{str(d)[:200]}"

    r = client.get(f"/api/v1/error-book/{item_id}", headers=_cookie(sid_b))
    assert r.status_code == 404, f"B 读 A 的错题 → {r.status_code}，期望 404"

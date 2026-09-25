"""治理服务与接口测试（G 板块 · #43/#46/#49/D39）。

覆盖：
1. 违规分级阶梯（#43）：1=warn，2–3=temp_ban，≥4=perm_ban；留痕完整；
2. get_active_sanction：temp_ban 过期后不再生效，perm_ban 永久；
3. 奖章幂等（#49）：同里程碑只授一次，非法里程碑拒绝；
4. POST /error-reports（#46）：消息级带上下文、设置常驻 messageId=null；
5. POST /analytics/events（D39）：payload 脱敏（手机号）、非法类别 400、
   响应返回脱敏后的实际落库内容；
6. GET /me/violations、GET /me/medals 只返回本人数据。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from database import SessionLocal
from governance_service import (
    TEMP_BAN_HOURS,
    award_milestone,
    get_active_sanction,
    record_violation,
    track_event,
)
from main import app
from models.governance import ViolationLog
from routes.governance import router as governance_router

# main.py 的 router 挂载归 X0（共享文件独占表）；测试进程内按 main.py 同样的
# /api/v1 前缀挂上以便打接口，main.py 源文件不动，PR 里提供挂载片段由 X0 合入。
# ⚠️ main.py 的 SPA catch-all（/{full_path:path}）注册在前，会把测试进程内
# 后挂载的 GET 路由吞掉（路由匹配按注册顺序），必须插到它前面。
def _mount_governance_router() -> None:
    from main import app

    # 幂等：pytest 同进程跑多个测试模块时会重复 import 本文件逻辑
    if any(getattr(r, "path", "") == "/api/v1/me/usage" for r in app.router.routes):
        return
    routes = app.router.routes
    n = len(routes)
    app.include_router(governance_router, prefix="/api/v1")
    gov = routes[n:]
    del routes[n:]
    catch_idx = next(
        i for i, r in enumerate(routes) if getattr(r, "path", "") == "/{full_path:path}"
    )
    for j, r in enumerate(gov):
        routes.insert(catch_idx + j, r)


_mount_governance_router()

client = TestClient(app)


def _actions(user_id: str) -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(ViolationLog)
            .filter(ViolationLog.user_id == user_id)
            .order_by(ViolationLog.level.asc())
            .all()
        )
        return [r.action for r in rows]
    finally:
        db.close()


def test_violation_ladder_1_warn_3_temp_ban_4_perm_ban():
    seq = [record_violation("u_vio1", "破甲诱导") for _ in range(4)]
    assert [s["action"] for s in seq] == ["warn", "temp_ban", "temp_ban", "perm_ban"]
    assert [s["level"] for s in seq] == [1, 2, 3, 4]
    # 留痕完整：reason 是命中类型，不是用户原文
    assert _actions("u_vio1") == ["warn", "temp_ban", "temp_ban", "perm_ban"]


def test_temp_ban_expires_and_perm_ban_never():
    # 第 1 次违规只是警告，不封禁；第 2 次起临时封禁
    record_violation("u_vio2", "滥用")
    assert get_active_sanction("u_vio2") is None
    record_violation("u_vio2", "滥用")
    s = get_active_sanction("u_vio2")
    assert s is not None and s["action"] == "temp_ban"
    assert s["until"] is not None and s["until"] > datetime.utcnow()

    # 把临时封禁的处置时间拨回 TEMP_BAN_HOURS+ 之前 → 过期不再生效
    db = SessionLocal()
    try:
        row = (
            db.query(ViolationLog)
            .filter(ViolationLog.user_id == "u_vio2", ViolationLog.action == "temp_ban")
            .order_by(ViolationLog.level.desc())
            .first()
        )
        row.created_at = datetime.utcnow() - timedelta(hours=TEMP_BAN_HOURS + 1)
        db.commit()
    finally:
        db.close()
    assert get_active_sanction("u_vio2") is None

    # 屡犯到第 4 次 → perm_ban，永久生效不受时间影响
    record_violation("u_vio2", "再次违规")  # level 3 → temp_ban
    record_violation("u_vio2", "再次违规")  # level 4 → perm_ban
    s = get_active_sanction("u_vio2")
    assert s is not None and s["action"] == "perm_ban" and s["until"] is None


def test_medal_idempotent_and_validated():
    first = award_milestone("u_medal1", "first_record")
    assert first is not None and first["milestone"] == "first_record"
    assert award_milestone("u_medal1", "first_record") is None  # 幂等
    assert award_milestone("u_medal1", "not_a_milestone") is None  # 非法里程碑
    assert award_milestone("u_medal2", "streak_7_days") is not None  # 不与他人互斥


def test_error_report_message_level_and_settings_level():
    # 消息级：带 messageId + intent + 上下文
    r = client.post(
        "/api/v1/error-reports",
        headers={"X-User-ID": "u_er1"},
        json={
            "messageId": "msg_abc",
            "intent": "search",
            "description": "这条回答答非所问",
            "context": {"role": "assistant", "intent": "search"},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["messageId"] == "msg_abc" and body["intent"] == "search"
    assert body["context"]["role"] == "assistant"

    # 设置常驻入口：messageId 为空
    r = client.post(
        "/api/v1/error-reports",
        headers={"X-User-ID": "u_er1"},
        json={"description": "设置里报个错"},
    )
    assert r.status_code == 201
    assert r.json()["messageId"] is None

    # description 必填且限长
    r = client.post("/api/v1/error-reports", headers={"X-User-ID": "u_er1"}, json={})
    assert r.status_code == 400


def test_analytics_event_sanitized_and_validated():
    # payload 里的手机号必须被脱敏后落库（响应即实际存储内容）
    r = client.post(
        "/api/v1/analytics/events",
        headers={"X-User-ID": "u_ae1"},
        json={
            "category": "chat_interaction",
            "eventType": "card_clicked",
            "sessionId": "cs_1",
            "payload": {"note": "联系我 13812345678", "cardType": "knowledge_point"},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["eventType"] == "card_clicked"
    assert "13812345678" not in (body["payload"] or {}).get("note", "")

    # 非法类别 → 400（全局校验异常统一 VALIDATION_FAILED）
    r = client.post(
        "/api/v1/analytics/events",
        headers={"X-User-ID": "u_ae1"},
        json={"category": "not_a_category", "eventType": "x"},
    )
    assert r.status_code == 400


def test_my_violations_and_medals_scoped_to_self():
    record_violation("u_scope1", "破甲诱导")
    award_milestone("u_scope1", "first_summary")

    r = client.get("/api/v1/me/violations", headers={"X-User-ID": "u_scope1"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["action"] == "warn"
    # 本人可查，他人不可见
    r = client.get("/api/v1/me/violations", headers={"X-User-ID": "u_scope2"})
    assert r.status_code == 200 and r.json()["items"] == []

    r = client.get("/api/v1/me/medals", headers={"X-User-ID": "u_scope1"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["milestone"] == "first_summary"
    assert items[0]["medalId"].startswith("md_")

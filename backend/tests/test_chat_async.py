"""带图 Chat 异步任务集成测试（契约 v1.13.0）。

覆盖验收点：
- 入队语义：202 + queued + jobId + **服务端下发的 pollAfterMs**（前端不写死节奏）
- 归属：别人的 mediaKey 403、别人的 job 403、不存在的 job 404
- 并发上限：同一用户第 5 个在途任务 429，且**不静默吞掉**用户刚拍的照片
- 终态必有结果：done 带正文 / failed 带可展示原因（**不允许用户干等**）
- 幂等：重复投递 worker 不会把 done 覆盖成 failed
- 重启对账：残留 queued/processing 置 failed + CHAT_JOB_INTERRUPTED，已终态不动
- 同步路径零回归：POST /chat 的响应形状一字未改

⚠️ TestClient 会**同步执行完 BackgroundTasks** 才返回，所以本文件里 POST 返回后
job 通常已是 done——这正好用来断言「一整轮真的跑通了」。要观察 queued 中间态
请直接查库（见 test_*_row_starts_as_queued）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

U = "u_10237"
OTHER = "u_99999"


def _hdr(user_id: str = U) -> dict:
    return {"X-User-ID": user_id}


class _FakeProvider:
    """固定文案供应商。"""

    def __init__(self, reply: str = "先看题干的第二个条件，再往下推。") -> None:
        self.reply = reply

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        return self.reply


class _BoomProvider:
    """模拟 worker 内部异常（LLM 挂了 / R2 炸了）。"""

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        raise RuntimeError("provider exploded")


def _stub_provider(monkeypatch, provider) -> None:
    import chat_engine

    monkeypatch.setattr(chat_engine, "get_provider", lambda: provider)


def _key(user_id: str = U) -> str:
    return f"user/{user_id}/2f1c9a7b.png"


# ---------------------------------------------------------------- 入队语义


def test_media_post_returns_202_queued_and_poll_hint(monkeypatch):
    _stub_provider(monkeypatch, _FakeProvider())
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "这道题怎么做？", "mediaKey": _key()},
        headers=_hdr(),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    # 202 只代表「已受理」，不代表有结果
    assert body["status"] == "queued"
    assert body["jobId"].startswith("cj_")
    # 轮询间隔由服务端下发，不写死在前端
    assert body["pollAfterMs"] == 2000
    assert body["acceptedAt"]
    # 202 里绝不能混进结果字段，否则前端会以为已经答完了
    assert "reply" not in body


def test_media_post_requires_media_key():
    """mediaKey 必填。走项目的 RequestValidationError → 400 VALIDATION_FAILED
    处理器（不是 FastAPI 默认的 422），与契约 '400': ValidationFailed 一致。"""
    r = client.post(
        "/api/v1/chat/media", json={"content": "无图"}, headers=_hdr()
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert r.json()["error"]["field"] == "mediaKey"


def test_row_starts_as_queued_before_worker_runs():
    """直接查库：入队那一刻状态就是 queued（worker 还没接手）。"""
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        db.add(
            ChatJob(
                id="cj_row_probe",
                user_id=U,
                status="queued",
                content="x",
                media_key=_key(),
            )
        )
        db.commit()
        row = db.get(ChatJob, "cj_row_probe")
        assert row.status == "queued"
        assert row.reply is None and row.completed_at is None
        # server_default 真生效
        assert row.crisis is False
    finally:
        db.close()


# ---------------------------------------------------------------- 终态结果


def test_job_completes_and_reports_done(monkeypatch):
    _stub_provider(monkeypatch, _FakeProvider("这道题要先提公因式。"))
    job_id = client.post(
        "/api/v1/chat/media",
        json={"content": "带图提问", "mediaKey": _key()},
        headers=_hdr(),
    ).json()["jobId"]

    r = client.get(f"/api/v1/chat/jobs/{job_id}", headers=_hdr())
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["status"] == "done", job
    assert job["reply"] == "这道题要先提公因式。"
    assert job["errorCode"] is None and job["errorMessage"] is None
    # done 时会话与上下文栈与同步 ChatReply 同义
    assert job["sessionId"]
    assert isinstance(job["cards"], list)
    assert isinstance(job["contextStack"], list)
    assert job["completedAt"]


def test_worker_failure_marks_failed_with_visible_reason(monkeypatch):
    """失败也必须有原因可展示——绝不能让用户对着转圈圈干等。"""
    _stub_provider(monkeypatch, _BoomProvider())
    job_id = client.post(
        "/api/v1/chat/media",
        json={"content": "带图提问", "mediaKey": _key()},
        headers=_hdr(),
    ).json()["jobId"]

    job = client.get(f"/api/v1/chat/jobs/{job_id}", headers=_hdr()).json()
    assert job["status"] == "failed", job
    assert job["errorCode"] == "CHAT_JOB_INTERNAL_ERROR"
    assert job["errorMessage"]
    assert job["reply"] is None
    assert job["completedAt"]


def test_failure_message_does_not_leak_internals(monkeypatch):
    """内部异常文案不该出现在学生面前。"""
    _stub_provider(monkeypatch, _BoomProvider())
    job_id = client.post(
        "/api/v1/chat/media",
        json={"content": "带图提问", "mediaKey": _key()},
        headers=_hdr(),
    ).json()["jobId"]
    job = client.get(f"/api/v1/chat/jobs/{job_id}", headers=_hdr()).json()
    assert "provider exploded" not in job["errorMessage"]
    assert "Traceback" not in job["errorMessage"]


# ---------------------------------------------------------------- 归属 / 存在性


def test_media_rejects_other_users_key_403():
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "别人的图", "mediaKey": _key(OTHER)},
        headers=_hdr(),
    )
    assert r.status_code == 403, r.text


def test_unknown_job_is_404():
    r = client.get("/api/v1/chat/jobs/cj_does_not_exist", headers=_hdr())
    assert r.status_code == 404, r.text


def test_other_users_job_is_403():
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        db.add(
            ChatJob(
                id="cj_someone_else",
                user_id=OTHER,
                status="queued",
                content="x",
                media_key=_key(OTHER),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/chat/jobs/cj_someone_else", headers=_hdr())
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------- 并发上限


def test_concurrency_cap_returns_429(monkeypatch):
    """在途任务达上限 → 429，且**不静默吞掉**用户刚拍的照片。"""
    _stub_provider(monkeypatch, _FakeProvider())
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        for i in range(4):  # MAX_ACTIVE_JOBS_PER_USER = 4
            db.add(
                ChatJob(
                    id=f"cj_active_{i}",
                    user_id=U,
                    status="queued",
                    content="x",
                    media_key=_key(),
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/chat/media",
        json={"content": "第 5 张", "mediaKey": _key()},
        headers=_hdr(),
    )
    assert r.status_code == 429, r.text
    assert "TOO_MANY_MEDIA_JOBS" in r.text


def test_concurrency_cap_is_per_user(monkeypatch):
    """上限是**每用户**的，不是全局的——一个人刷满不能拖垮别人。"""
    _stub_provider(monkeypatch, _FakeProvider())
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        for i in range(4):
            db.add(
                ChatJob(
                    id=f"cj_cap_{i}",
                    user_id=OTHER,
                    status="processing",
                    content="x",
                    media_key=_key(OTHER),
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/chat/media",
        json={"content": "我自己的", "mediaKey": _key()},
        headers=_hdr(),
    )
    assert r.status_code == 202, r.text


def test_finished_jobs_do_not_count_toward_cap(monkeypatch):
    """终态任务不占额度，否则用户问满 4 次之后就永久被锁死。"""
    _stub_provider(monkeypatch, _FakeProvider())
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        for i in range(6):
            db.add(
                ChatJob(
                    id=f"cj_done_{i}",
                    user_id=U,
                    status="done",
                    content="x",
                    media_key=_key(),
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/chat/media",
        json={"content": "还能问", "mediaKey": _key()},
        headers=_hdr(),
    )
    assert r.status_code == 202, r.text


# ---------------------------------------------------------------- 幂等 / 重启对账


def test_worker_is_idempotent_on_terminal_job():
    """重复投递不能把 done 覆盖成 failed。"""
    from chat_jobs import run_chat_job
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        db.add(
            ChatJob(
                id="cj_idem",
                user_id=U,
                status="done",
                content="x",
                media_key=_key(),
                reply="已经答过了",
            )
        )
        db.commit()
    finally:
        db.close()

    run_chat_job("cj_idem")

    db = SessionLocal()
    try:
        row = db.get(ChatJob, "cj_idem")
        assert row.status == "done"
        assert row.reply == "已经答过了"
        assert row.error_code is None
    finally:
        db.close()


def test_reconcile_marks_stale_jobs_failed():
    """重启对账：残留 queued/processing 置 failed + CHAT_JOB_INTERRUPTED。"""
    from chat_jobs import reconcile_on_startup
    from database import SessionLocal
    from models.chat import ChatJob

    db = SessionLocal()
    try:
        db.add(
            ChatJob(
                id="cj_stale_q",
                user_id=U,
                status="queued",
                content="x",
                media_key=_key(),
            )
        )
        db.add(
            ChatJob(
                id="cj_stale_p",
                user_id=U,
                status="processing",
                content="x",
                media_key=_key(),
            )
        )
        db.add(
            ChatJob(
                id="cj_settled",
                user_id=U,
                status="done",
                content="x",
                media_key=_key(),
                reply="好了",
            )
        )
        db.commit()
    finally:
        db.close()

    n = reconcile_on_startup()
    assert n == 2, n

    db = SessionLocal()
    try:
        for jid in ("cj_stale_q", "cj_stale_p"):
            row = db.get(ChatJob, jid)
            assert row.status == "failed", row.status
            assert row.error_code == "CHAT_JOB_INTERRUPTED"
            assert row.error_message
            assert row.completed_at is not None
        settled = db.get(ChatJob, "cj_settled")
        assert settled.status == "done"
        assert settled.error_code is None
        # 幂等：再跑一次不该重复计数
        assert reconcile_on_startup() == 0
    finally:
        db.close()


def test_interrupted_job_is_visible_to_user():
    """对账置的 failed 对用户可见（不是静默消失）。"""
    from database import SessionLocal
    from models.chat import ChatJob
    from chat_jobs import reconcile_on_startup

    db = SessionLocal()
    try:
        db.add(
            ChatJob(
                id="cj_int_visible",
                user_id=U,
                status="processing",
                content="x",
                media_key=_key(),
            )
        )
        db.commit()
    finally:
        db.close()
    reconcile_on_startup()

    job = client.get("/api/v1/chat/jobs/cj_int_visible", headers=_hdr()).json()
    assert job["status"] == "failed"
    assert job["errorCode"] == "CHAT_JOB_INTERRUPTED"
    assert "再发一次" in job["errorMessage"]


# ---------------------------------------------------------------- 同步路径零回归


def test_sync_chat_path_unchanged(monkeypatch):
    """同步 POST /chat 必须仍是 200 + reply（这一格是整个方案存在的前提）。"""
    _stub_provider(monkeypatch, _FakeProvider("同步路径照常工作。"))
    r = client.post("/api/v1/chat", json={"content": "纯文本"}, headers=_hdr())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "同步路径照常工作。"
    assert body["sessionId"]
    assert "jobId" not in body


def test_sync_chat_still_accepts_media_key(monkeypatch):
    """带图**同步**路径保留（浮窗/低延迟场景仍可用），本轮没动它。"""
    _stub_provider(monkeypatch, _FakeProvider("带图同步也还在。"))
    r = client.post(
        "/api/v1/chat",
        json={"content": "带图但同步", "mediaKey": _key()},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "带图同步也还在。"


# ---------------------------------------------------------------- 契约形状守卫


def test_schema_field_names_match_contract_exactly():
    """pydantic 序列化后的字段名必须与契约 properties **完全一致**。

    这个测试是被真实 bug 逼出来的：created_at / error_code / error_message
    三处漏写 ``alias=``，pydantic 就按 snake_case 序列化，前端拿不到
    ``errorCode``，失败原因**静默消失**——而契约里恰恰要求「不允许用户干等」。

    靠 review 记性防不住这类错误，所以钉死成测试。
    """
    from pathlib import Path

    import yaml

    from schemas.chat import (
        ChatJob as JobS,
        ChatMediaJobAccepted as AccS,
        ChatMediaJobRequest as ReqS,
    )

    spec = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    for name, model in (
        ("ChatJob", JobS),
        ("ChatMediaJobAccepted", AccS),
        ("ChatMediaJobRequest", ReqS),
    ):
        contract_props = set(spec["components"]["schemas"][name]["properties"])
        # by_alias=True 才是真实上线的序列化口径
        model_props = set(model.model_json_schema(by_alias=True)["properties"])
        assert model_props == contract_props, (
            f"{name} 字段名与契约不一致\n"
            f"  契约有 / 模型无: {sorted(contract_props - model_props)}\n"
            f"  模型有 / 契约无: {sorted(model_props - contract_props)}"
        )


def test_no_snake_case_leaks_into_job_response(monkeypatch):
    """真实响应里不能混进 snake_case 字段名。"""
    _stub_provider(monkeypatch, _FakeProvider())
    job_id = client.post(
        "/api/v1/chat/media",
        json={"content": "带图提问", "mediaKey": _key()},
        headers=_hdr(),
    ).json()["jobId"]
    keys = set(
        client.get(f"/api/v1/chat/jobs/{job_id}", headers=_hdr()).json().keys()
    )
    snake = {k for k in keys if "_" in k}
    assert not snake, f"响应混入 snake_case 字段: {sorted(snake)}"
    for must in ("jobId", "status", "crisis", "cards", "contextStack", "createdAt"):
        assert must in keys, f"响应缺字段 {must}（实际: {sorted(keys)}）"

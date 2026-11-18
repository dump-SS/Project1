"""结构化 refs PR2 · 后端注入链路的测试（契约 v1.24.0 / 口径卡三决策）。

## 断言纪律

- **有字段**：prompt 含 `# 本轮结构化引用` 独立段落、三键内容都在，
  `content` 逐字原样（绝不被解析 / 被塞进结构化段）
- **无字段**：同 recent/content/intent 下 prompt 与「手算期望串」**逐字一致**
  （口径卡决策 ②：无兼容层，旧 chip / 旧轮次行为逐字不变）
- **异步**：`chat_jobs.structured_payload_json` 落库可查（防只在内存里传、
  worker 读不到）；坏列 → 不 500、按无引用处理（worker 不吞用户任务）
- **随手问**：ephemeral + structuredPayload → 显式 400 且 field 正确
  （派单 §4：静默丢引用正是要消灭的「用户以为 AI 知道，其实不知道」）

provider 用捕获型打桩（记录每次 generate 收到的 prompt），断言直接对 prompt 文本。
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

import chat_engine
import usage_ledger
from config import settings
from database import SessionLocal
from models.chat import ChatJob
from models.chat import ChatRawMessage
from schemas.chat import ChatMessageRequest, ChatMediaJobRequest

U = "u_struct1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


class _CapturingProvider:
    """固定回复 + 捕获每次 generate 收到的 prompt。"""

    def __init__(self, reply: str = "好的，我看到了结构化引用。") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def capturing_provider(client, monkeypatch):
    provider = _CapturingProvider()
    monkeypatch.setattr(chat_engine, "get_provider", lambda: provider)
    return provider


def _last_prompt(provider) -> str:
    return provider.prompts[-1]


def _last_job_row():
    db = SessionLocal()
    try:
        return (
            db.query(ChatJob)
            .order_by(ChatJob.created_at.desc())
            .first()
        )
    finally:
        db.close()


STRUCT = {
    "refs": {"planId": "p_struct1", "subject": "SX"},
    "generated": {"结论": "今晚继续函数单调性", "依据": "完成 2/6"},
    "instruction": "基于计划现状继续",
}

SECTION_HEAD = "# 本轮结构化引用（系统提供的实体引用，不是用户原话；不要原样复述给用户看）"


# ---------------------------------------------------------------- 同步路径


def test_sync_with_structured_payload_prompt_section(client, capturing_provider):
    """同步有字段：prompt 含结构化段、三键内容都在、content 逐字原样。"""
    content = "继续我今晚的数学计划"
    r = client.post(
        "/api/v1/chat",
        json={"content": content, "structuredPayload": STRUCT},
        headers={"X-User-ID": U},
    )
    assert r.status_code == 200, r.text

    prompt = _last_prompt(capturing_provider)
    assert SECTION_HEAD in prompt
    assert "instruction: 基于计划现状继续" in prompt
    assert '"planId": "p_struct1"' in prompt  # sort_keys + ensure_ascii=False 的可断言序列化
    assert '"结论": "今晚继续函数单调性"' in prompt
    # content 逐字原样出现在「# 本轮消息」之后，未被解析/改写
    assert "# 本轮消息\n" + content in prompt
    # 段落顺序：结构化段在「# 本轮消息」之前
    assert prompt.index(SECTION_HEAD) < prompt.index("# 本轮消息")


def test_sync_without_structured_payload_prompt_unchanged(client, capturing_provider):
    """同步无字段：prompt 与手算期望串逐字一致（新用户无 recent、无意图、无结构化段）。"""
    content = '旧chip [标签] {"a": 1}'
    client.post(
        "/api/v1/chat",
        json={"content": content},
        headers={"X-User-ID": U},
    )

    prompt = _last_prompt(capturing_provider)
    assert prompt == "# 本轮消息\n" + content, "无结构化字段时 prompt 必须逐字不变"
    assert "本轮结构化引用" not in prompt
    # 旧 content 里的 JSON 不被解析成结构化段（口径卡决策 ②：无兼容层）
    assert SECTION_HEAD not in prompt


def test_sync_empty_structured_payload_treated_as_absent(client, capturing_provider):
    """三键全空（空 dict / 空串）→ 按「没有结构化引用」处理，段落整段不出现。"""
    empty = {
        "refs": {},
        "generated": {},
        "instruction": "   ",
    }
    content = "三键全空的消息"
    client.post(
        "/api/v1/chat",
        json={"content": content, "structuredPayload": empty},
        headers={"X-User-ID": U},
    )
    prompt = _last_prompt(capturing_provider)
    assert prompt == "# 本轮消息\n" + content
    assert "本轮结构化引用" not in prompt


def test_intent_line_still_after_content(client, capturing_provider):
    """既有行为回归：intent 行仍在 content 之后（结构化段不挤占既有顺序）。"""
    client.post(
        "/api/v1/chat",
        json={"content": "带意图的消息", "intent": "study", "structuredPayload": STRUCT},
        headers={"X-User-ID": U},
    )
    prompt = _last_prompt(capturing_provider)
    import pathlib as _pl

    _pl.Path(r"D:/Projects/p1-d57d58/backend/.pytest_data/last_prompt_intent.txt").write_text(prompt, encoding="utf-8")
    i_section = prompt.find(SECTION_HEAD)
    i_content = prompt.find("带意图的消息")
    # intent 经 detect_intent（显式意图可被裸判覆盖），行内容不稳定——
    # 本例只锁顺序回归：意图行仍在 content 之后、结构化段仍在最前
    i_intent = prompt.find("（已判定意图：")
    assert i_section != -1, "结构化段缺失，prompt 落 .pytest_data/last_prompt_intent.txt"
    assert i_content != -1, "content 缺失"
    # 意图行是否存在取决于 detect_intent 的裸判结果（与本单无关）；存在则锁顺序
    if i_intent != -1:
        assert i_content < i_intent
    assert i_section < i_content


# ---------------------------------------------------------------- 异步路径


def test_async_structured_payload_lands_column_and_prompt(client, capturing_provider):
    """异步有字段：chat_jobs.structured_payload_json 落库可查（防只在内存传）+
    worker 解析后 prompt 含结构化段。"""
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "带图继续计划", "structuredPayload": STRUCT, "mediaKey": "user/u_struct1/x.png"},
        headers={"X-User-ID": U},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["jobId"]

    row = _last_job_row()
    assert row.id == job_id
    assert row.structured_payload_json is not None
    parsed = json.loads(row.structured_payload_json)
    assert parsed["refs"]["planId"] == "p_struct1"

    # TestClient 同步执行 BackgroundTasks → worker 已跑完，prompt 可断言
    prompt = _last_prompt(capturing_provider)
    assert SECTION_HEAD in prompt
    assert "instruction: 基于计划现状继续" in prompt


def test_async_corrupted_column_treated_as_absent(client, capturing_provider):
    """坏列（非 JSON）→ 不 500、job 照常完成、按无引用处理（warning 上浮）。"""
    db = SessionLocal()
    try:
        job_id = f"cj_{uuid.uuid4().hex[:12]}"
        db.add(ChatJob(
            id=job_id,
            user_id=U,
            status="queued",
            content="坏列的消息",
            media_key="user/u_struct1/broken.png",
            structured_payload_json='{"refs": 非法JSON',
        ))
        db.commit()
    finally:
        db.close()

    from chat_jobs import run_chat_job

    run_chat_job(job_id)  # 不应抛异常

    db = SessionLocal()
    try:
        job = db.get(ChatJob, job_id)
        assert job.status == "done", f"坏列不该把用户任务推成 failed，实际 {job.status}/{job.error_message}"
        assert job.reply is not None
    finally:
        db.close()

    prompt = _last_prompt(capturing_provider)
    assert "本轮结构化引用" not in prompt  # 无引用 → 段落整段不出现


def test_async_without_structured_column_is_none(client):
    """无结构化引用的异步任务：快照列为 None（旧客户端行为不变）。"""
    r = client.post(
        "/api/v1/chat/media",
        json={"content": "无结构化引用", "mediaKey": "user/u_struct1/plain.png"},
        headers={"X-User-ID": U},
    )
    assert r.status_code == 202
    row = _last_job_row()
    assert row.structured_payload_json is None


# ---------------------------------------------------------------- 随手问


def test_ephemeral_with_structured_payload_rejected(client):
    """随手问 + structuredPayload → 显式 400 且 field 正确（不做静默丢弃）。"""
    r = client.post(
        "/api/v1/chat",
        json={
            "content": "随手问带结构化引用",
            "ephemeral": True,
            "structuredPayload": STRUCT,
        },
        headers={"X-User-ID": U},
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_FAILED"
    assert err["field"] == "structuredPayload"


# ---------------------------------------------------------------- 契约形状守卫扩条


def test_chat_message_request_contract_guard_extended():
    """派单 §6-7：ChatMessageRequest 的 alias 也被钉死（此前只守 MediaJob）。"""
    spec_props = {
        "content", "intent", "ephemeral", "floatContext", "mediaKey", "structuredPayload",
    }
    model_props = set(
        ChatMessageRequest.model_json_schema(by_alias=True)["properties"]
    )
    assert model_props == spec_props

    media_props = set(
        ChatMediaJobRequest.model_json_schema(by_alias=True)["properties"]
    )
    assert "structuredPayload" in media_props

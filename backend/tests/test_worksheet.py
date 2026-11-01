"""D55 · 作业单抽取端点 + PlanCreate.tasks 覆写路径的测试（契约 v1.15.0）。

## 隔离方式（与 test_f_media.py 同款）

- **不真调 R2**：get_object monkeypatch 成假实现；
- **不真调 LLM**：worksheet_extract.get_provider 换成返回固定 JSON 的假 provider
  （conftest 已把全局 LLM_PROVIDER 设为 mock，这里再换是因为要精确控制
  「返回什么原文」——垃圾输出/空串/合法 JSON 三态都要能造出来）。

## 测试重心

1. 归属：别人的 key 403，且 **R2 与 LLM 都没被触达**（与 f_media 同一口径）；
2. 抽取归一化：subject 大小写归一 / 越界分钟截断 / 未知学科兜底 other / 超 20 项截断；
3. LLM 失败语义：垃圾输出、空串 → 502 EXTRACT_FAILED（不是裸 500）；
4. R2 分档：不存在 404、未配置 503、其他 R2 故障 502；
5. 计划落库：tasks 覆写路径——显式任务按序入计划、priority 1..n、adaptedFrom 为 null、
   goalIds 被忽略；>20 条 / 分钟越界 → 422（pydantic 挡在门外）。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import r2_storage
import worksheet_extract
from config import settings

# 1x1 像素 PNG（魔数 + 合法 IHDR）——抽取端点不校验图片内容，取到字节就送模型
PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
)

MY_KEY = "user/u_test1/abc123.png"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


@pytest.fixture
def fake_llm(monkeypatch):
    """把 worksheet_extract 的 provider 换成可控假货；用 set_response 指定本次原文。"""
    holder: dict = {"text": None, "called": 0}

    class FakeProvider:
        def generate(self, prompt, context=None):
            holder["called"] += 1
            return holder["text"]

    monkeypatch.setattr(worksheet_extract, "get_provider", lambda: FakeProvider())
    return holder


@pytest.fixture
def r2_get(monkeypatch):
    """get_object 假实现：返回 PNG 字节；记录调用过的 key（越权断言用）。"""
    called: list[str] = []

    def fake_get(key):
        called.append(key)
        return PNG, "image/png"

    monkeypatch.setattr(r2_storage, "get_object", fake_get)
    return called


def _extract_body() -> dict:
    return {"mediaKey": MY_KEY}


# ---------------------------------------------------------------- 抽取：归属


def test_extract_other_users_key_403_and_no_side_effect(client, monkeypatch):
    """别人的 key → 403，且 R2 / LLM 都不触达（越权连读都不该发生）。"""
    llm_called = {"n": 0}

    class ShouldNotRun:
        def generate(self, prompt, context=None):
            llm_called["n"] += 1
            return "[]"

    monkeypatch.setattr(worksheet_extract, "get_provider", lambda: ShouldNotRun())
    resp = client.post(
        "/api/v1/f/worksheet/extract",
        json={"mediaKey": "user/u_other/x.png"},
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 403
    assert llm_called["n"] == 0


def test_extract_traversal_key_403(client):
    resp = client.post(
        "/api/v1/f/worksheet/extract",
        json={"mediaKey": "../embeddings.index"},
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------- 抽取：归一化


def test_extract_happy_path_normalizes(client, fake_llm, r2_get):
    """subject 大小写归一、未知学科兜底 other、越界分钟截断、topic 去空白。"""
    fake_llm["text"] = json.dumps([
        {"subject": "sx", "topic": " 数学练习册 P32 第 1-8 题 ", "estimatedMinutes": 3000},
        {"subject": "mystery", "topic": "奇怪的学科", "estimatedMinutes": 0},
        {"subject": "YW", "topic": "背课文", "estimatedMinutes": 25},
    ])
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    assert items[0]["subject"] == "SX"
    assert items[0]["estimatedMinutes"] == 240  # 3000 → 截到上限
    assert items[1]["subject"] == "other"  # 未知学科兜底
    assert items[1]["estimatedMinutes"] == 5  # 0 → 截到下限
    assert items[2]["estimatedMinutes"] == 25
    # 出域计量需要 user_id 进 context：假 provider 收到的 context 必须带
    assert r2_get == [MY_KEY]


def test_extract_fenced_json_tolerated(client, fake_llm, r2_get):
    """推理模型常带 ```json 围栏或前后说明文字——截取首尾方括号后仍要能解析。"""
    fake_llm["text"] = "好的，识别结果如下：\n```json\n" + json.dumps([
        {"subject": "SX", "topic": "口算 20 题", "estimatedMinutes": 20},
    ]) + "\n```\n以上就是全部作业。"
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["topic"] == "口算 20 题"


def test_extract_more_than_20_items_capped(client, fake_llm, r2_get):
    fake_llm["text"] = json.dumps(
        [{"subject": "SX", "topic": f"第 {i} 题", "estimatedMinutes": 10} for i in range(35)]
    )
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 20


def test_extract_fallback_item(client, fake_llm, r2_get):
    """照片里没有作业：模型按 prompt 返回单条兜底项，原样透传。"""
    fake_llm["text"] = json.dumps([
        {"subject": "other", "topic": "未识别到作业项", "estimatedMinutes": 20},
    ])
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == [
        {"subject": "other", "topic": "未识别到作业项", "estimatedMinutes": 20}
    ]


# ---------------------------------------------------------------- 抽取：失败语义


def test_extract_llm_none_502(client, fake_llm, r2_get):
    fake_llm["text"] = None
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "EXTRACT_FAILED"


def test_extract_llm_garbage_502(client, fake_llm, r2_get):
    fake_llm["text"] = "我觉得这张照片拍得不错，但没有作业。"
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "EXTRACT_FAILED"


# ---------------------------------------------------------------- 抽取：R2 分档


def test_extract_media_missing_404(client, monkeypatch):
    def boom(key):
        raise r2_storage.R2Error("R2 GET 失败：HTTP 404", status=404)

    monkeypatch.setattr(r2_storage, "get_object", boom)
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_extract_r2_offline_503(client, monkeypatch):
    def boom(key):
        raise r2_storage.R2NotConfigured("no creds")

    monkeypatch.setattr(r2_storage, "get_object", boom)
    resp = client.post(
        "/api/v1/f/worksheet/extract", json=_extract_body(), headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------- 计划落库：tasks 覆写


def test_create_plan_with_tasks_override(client):
    """显式任务直接落计划：按序、priority 1..n、无 goal 关联、adaptedFrom 为 null。"""
    resp = client.post(
        "/api/v1/plans",
        json={
            "planDate": "2026-11-02",
            "availableMinutes": 60,
            "tasks": [
                {"subject": "SX", "topic": "数学练习册 P32", "estimatedMinutes": 40},
                {"subject": "YY", "topic": "背 Unit 3 单词", "estimatedMinutes": 20},
            ],
        },
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 201
    plan = resp.json()
    assert [t["topic"] for t in plan["tasks"]] == ["数学练习册 P32", "背 Unit 3 单词"]
    assert [t["priority"] for t in plan["tasks"]] == [1, 2]
    assert [t["estimatedMinutes"] for t in plan["tasks"]] == [40, 20]
    assert all(t["goalId"] is None for t in plan["tasks"])
    assert plan["adaptedFrom"] is None  # 显式任务不做疲劳降载，也无处挂评估


def test_create_plan_tasks_ignore_goal_ids(client):
    """tasks 与 goalIds 互斥：同时传时 goalIds 被忽略（即便 id 是编的也不 404）。"""
    resp = client.post(
        "/api/v1/plans",
        json={
            "planDate": "2026-11-02",
            "availableMinutes": 30,
            "goalIds": ["g_nonexistent"],
            "tasks": [{"subject": "SX", "topic": "口算 20 题", "estimatedMinutes": 30}],
        },
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 201
    assert resp.json()["tasks"][0]["topic"] == "口算 20 题"


def test_create_plan_tasks_conflict_still_409(client):
    """同 planDate 已有计划时，tasks 路径与规则引擎路径一样要吃 409（regenerate 语义不变）。"""
    body = {
        "planDate": "2026-11-02",
        "availableMinutes": 30,
        "tasks": [{"subject": "SX", "topic": "口算", "estimatedMinutes": 30}],
    }
    first = client.post("/api/v1/plans", json=body, headers={"X-User-ID": "u_test1"})
    assert first.status_code == 201
    second = client.post("/api/v1/plans", json=body, headers={"X-User-ID": "u_test1"})
    assert second.status_code == 409
    regen = client.post(
        "/api/v1/plans", json={**body, "regenerate": True}, headers={"X-User-ID": "u_test1"}
    )
    assert regen.status_code == 201


def test_create_plan_tasks_validation_400(client):
    """>20 条 / 分钟越界：pydantic 校验失败，经全局异常处理器归一为 400 VALIDATION_FAILED
    （本项目把 RequestValidationError 统一映射成 400，不是 FastAPI 默认的 422）。"""
    too_many = {
        "planDate": "2026-11-02",
        "availableMinutes": 600,
        "tasks": [
            {"subject": "SX", "topic": f"第 {i} 题", "estimatedMinutes": 10} for i in range(21)
        ],
    }
    assert (
        client.post("/api/v1/plans", json=too_many, headers={"X-User-ID": "u_test1"}).status_code
        == 400
    )
    bad_minutes = {
        "planDate": "2026-11-02",
        "availableMinutes": 60,
        "tasks": [{"subject": "SX", "topic": "口算", "estimatedMinutes": 1}],
    }
    assert (
        client.post("/api/v1/plans", json=bad_minutes, headers={"X-User-ID": "u_test1"}).status_code
        == 400
    )


def test_create_plan_without_tasks_unchanged(client):
    """不传 tasks：规则引擎路径行为不变（无目标时走 P0-1 兜底任务）。"""
    resp = client.post(
        "/api/v1/plans",
        json={"planDate": "2026-11-02", "availableMinutes": 60},
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 201
    plan = resp.json()
    assert len(plan["tasks"]) >= 1

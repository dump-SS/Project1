"""#47 · 照片要点摘要端点的测试（契约 v1.18.0）。

## 测试重心（M5 验收门：「摘要入库前脱敏（测试）」）

**脱敏是本单的合规核心**：LLM 摘要里若带出个人信息，入库即违规。
测试直接喂「模型吐了含手机号/身份证的摘要」这一最坏情形，断言端点返回的
文本已脱敏——这验证的是**源头防线**（media_summary.summarize_media 内部
调用 privacy_filter），不是某个消费方的自觉。

其余：归属校验（别人的 key 403 且 R2/LLM 不触达）、R2 分档（404/503/502）、
LLM 失败语义（None/垃圾 → 502 SUMMARY_FAILED）、subject 归一。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import r2_storage
import media_summary
from config import settings

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
    holder: dict = {"text": None, "contexts": []}

    class FakeProvider:
        def generate(self, prompt, context=None):
            holder["contexts"].append(context)
            return holder["text"]

    monkeypatch.setattr(media_summary, "get_provider", lambda: FakeProvider())
    return holder


@pytest.fixture
def r2_get(monkeypatch):
    called: list[str] = []

    def fake_get(key):
        called.append(key)
        return PNG, "image/png"

    monkeypatch.setattr(r2_storage, "get_object", fake_get)
    return called


def _summary_json(subject: str, summary: str) -> str:
    return json.dumps({"subject": subject, "summary": summary})


# ---------------------------------------------------------------- 脱敏（M5 门）


def test_summary_sanitized_before_return(client, fake_llm, r2_get):
    """🔴 M5 验收门：模型在摘要里带出个人信息 → 端点返回前必须脱掉。

    这是「入库前脱敏」的源头防线测试：不管之后谁把这段文本存进收藏，
    拿到时就已经是脱敏版。
    """
    fake_llm["text"] = _summary_json(
        "SX",
        "- 练习册 P32 共 8 题\n- 联系张同学：13812345678\n- 抄送邮箱 sili@example.com",
    )
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert "13812345678" not in summary, "手机号未脱敏——M5 合规门失守"
    assert "sili@example.com" not in summary, "邮箱未脱敏——M5 合规门失守"
    assert "***" in summary, "敏感信息应被替换为 ***"


def test_summary_id_card_sanitized(client, fake_llm, r2_get):
    fake_llm["text"] = _summary_json(
        "other", "- 登记表上有身份证 110101200801011234 需要抄写"
    )
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    assert "110101200801011234" not in resp.json()["summary"]


def test_summary_clean_text_untouched(client, fake_llm, r2_get):
    """无敏感信息的正常摘要原样通过（脱敏不该误伤学习内容）。"""
    clean = "- 练习册 P32 共 8 题\n- 考查二次函数图像"
    fake_llm["text"] = _summary_json("SX", clean)
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == clean


# ---------------------------------------------------------------- 基本行为


def test_summary_happy_path(client, fake_llm, r2_get):
    fake_llm["text"] = _summary_json("sx", "- 口算 20 题\n- 应用题 3 道")
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "SX"  # 大小写归一
    assert body["summary"].startswith("- ")
    assert r2_get == [MY_KEY]
    # 出域计量需要 user_id 进 context
    assert fake_llm["contexts"][0]["user_id"] == "u_test1"
    assert fake_llm["contexts"][0]["feature_tier"] == "multimodal"


def test_summary_unknown_subject_fallback(client, fake_llm, r2_get):
    fake_llm["text"] = _summary_json("mystery", "- 看不懂的照片")
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    assert resp.json()["subject"] == "other"


def test_summary_unrecognizable_photo_fallback(client, fake_llm, r2_get):
    """模型按 prompt 返回兜底文案 → 原样透传。"""
    fake_llm["text"] = _summary_json("other", "照片内容无法辨认")
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == "照片内容无法辨认"


# ---------------------------------------------------------------- 失败语义


def test_summary_llm_none_502(client, fake_llm, r2_get):
    fake_llm["text"] = None
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "SUMMARY_FAILED"


def test_summary_llm_garbage_502(client, fake_llm, r2_get):
    fake_llm["text"] = "这张照片光线不错。"
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "SUMMARY_FAILED"


# ---------------------------------------------------------------- 归属与 R2 分档


def test_summary_other_users_key_403_no_side_effect(client, monkeypatch):
    llm_called = {"n": 0}
    r2_called = {"n": 0}

    class ShouldNotRun:
        def generate(self, prompt, context=None):
            llm_called["n"] += 1
            return "{}"

    monkeypatch.setattr(media_summary, "get_provider", lambda: ShouldNotRun())

    def fake_get(key):
        r2_called["n"] += 1
        return PNG, "image/png"

    monkeypatch.setattr(r2_storage, "get_object", fake_get)

    resp = client.post(
        "/api/v1/f/media/user/u_other/x.png/summary", headers={"X-User-ID": "u_test1"}
    )
    assert resp.status_code == 403
    assert llm_called["n"] == 0 and r2_called["n"] == 0


def test_summary_traversal_key_403(client):
    # URL 与 f_media 既有穿越测试同款构造：.. 嵌在用户前缀内，
    # 客户端不会归一化它，请求能到达 _assert_owner 的二次防线
    resp = client.post(
        "/api/v1/f/media/user/u_test1/../../embeddings.index/summary",
        headers={"X-User-ID": "u_test1"},
    )
    assert resp.status_code == 403


def test_summary_media_missing_404(client, monkeypatch):
    def boom(key):
        raise r2_storage.R2Error("R2 GET 失败：HTTP 404", status=404)

    monkeypatch.setattr(r2_storage, "get_object", boom)
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 404


def test_summary_r2_offline_503(client, monkeypatch):
    def boom(key):
        raise r2_storage.R2NotConfigured("no creds")

    monkeypatch.setattr(r2_storage, "get_object", boom)
    resp = client.post(f"/api/v1/f/media/{MY_KEY}/summary", headers={"X-User-ID": "u_test1"})
    assert resp.status_code == 503

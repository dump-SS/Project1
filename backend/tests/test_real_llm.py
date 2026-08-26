"""真实 LLM 集成测试——仅在配置了真实 API key 时执行，否则整文件 skip。

跑法（本地手动，不要进 CI）：
    cd backend
    # .env 里配好 LLM_PROVIDER=openai_compatible / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
    .venv/Scripts/python -m pytest tests/test_real_llm.py -v

当前接入的供应商：aiping.cn（Step-3.5-Flash），OpenAI 兼容 Bearer 鉴权。
耗时警告：每个用例真实调用一次 LLM，约 10-30 秒。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import settings

# 没配 key 时全部跳过——CI 和队友本地默认不触发真实调用
pytestmark = pytest.mark.skipif(
    settings.llm_provider == "mock" or not settings.llm_api_key,
    reason="未配置真实 LLM（LLM_PROVIDER/LLM_API_KEY），跳过真实调用测试",
)


@pytest.fixture(scope="module")
def client():
    from main import app

    return TestClient(app)


def _post_record(client, hour: str, focus: int = 5, fatigue: int = 1):
    return client.post(
        "/api/v1/learning-records",
        json={
            "subject": "SX",
            "startedAt": f"2026-08-12T{hour}:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed", "accuracy": 0.85, "interruptions": 0},
            "selfReport": {
                "focus": focus,
                "fatigue": fatigue,
                "emotion": "positive",
                "difficultyFeel": "easy",
            },
        },
    )


def test_real_llm_generates_llm_source_recommendation(client):
    """端到端：3 条记录 → POST 第 3 条 → GET /recommendations/{id} 应为 source=llm。

    若 LLM 超时/解析失败会退到 template——那也是合法路径，但本测试要确认
    主路径（真实 LLM 生成）能通，所以断言 source 必须是 llm。
    """
    for h in ["08", "09", "10"]:
        r = _post_record(client, h)
        assert r.status_code == 201

    rec_id = r.json()["recommendation"]["recommendationId"]
    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200

    body = detail.json()
    assert body["generation"]["status"] == "ready"
    assert body["generation"]["source"] == "llm", (
        f"预期走真实 LLM，实际 source={body['generation'].get('source')}；"
        "可能是超时/解析失败，查看上方 llm_provider 日志"
    )
    assert body["items"], "source=llm 时 items 不应为空"
    for item in body["items"]:
        assert item["title"]
        assert item["content"]

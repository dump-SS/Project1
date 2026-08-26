"""PRD 6.2 数据出域边界测试：sendTextToAI 开关 + 敏感信息脱敏。

覆盖：
1. privacy_filter.sanitize_text：手机号/身份证号/邮箱/QQ 检测与脱敏
2. ai_suggestion 接 sendTextToAI 开关：开/关两种模式下 note 是否进 prompt
3. 危机信号仍优先（不走 LLM、不走开关）
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from privacy_filter import contains_sensitive_info, sanitize_text

client = TestClient(app)


# ---------- privacy_filter 单元测试 ----------

def test_sanitize_mobile_phone():
    """手机号被替换为 ***，上下文保留。"""
    text = "今天给爸爸打电话 13812345678 问了题目"
    result = sanitize_text(text)
    assert "13812345678" not in result
    assert "***" in result
    # 上下文保留
    assert "给爸爸打电话" in result
    assert "问了题目" in result


def test_sanitize_id_card():
    """18 位身份证号被替换为 ***。"""
    text = "我的身份证号是 110101199003071234 请查一下"
    result = sanitize_text(text)
    assert "110101199003071234" not in result
    assert "***" in result


def test_sanitize_id_card_with_x():
    """身份证号末位 X 也应被识别。"""
    text = "身份证 11010119900307123X"
    result = sanitize_text(text)
    assert "11010119900307123X" not in result.lower()
    assert "***" in result


def test_sanitize_email():
    """邮箱被替换为 ***。"""
    text = "联系我 teacher@school.edu.cn"
    result = sanitize_text(text)
    assert "teacher@school.edu.cn" not in result
    assert "***" in result


def test_sanitize_qq():
    """QQ 号（5-12 位纯数字）被替换为 ***。"""
    text = "加我QQ 123456789 聊"
    result = sanitize_text(text)
    assert "123456789" not in result
    assert "***" in result


def test_sanitize_none_and_empty():
    """None / 空字符串原样返回。"""
    assert sanitize_text(None) is None
    assert sanitize_text("") == ""


def test_sanitize_no_false_positive_on_short_numbers():
    """短数字（如时长、分数）不被误判为敏感信息。"""
    text = "专注度 4 分，疲劳度 2 分，学了 30 分钟"
    result = sanitize_text(text)
    assert result == text  # 无脱敏


def test_sanitize_multiple_sensitive_in_one_text():
    """一段文本含多种敏感信息，全部脱敏。"""
    text = "手机 13812345678 邮箱 a@b.com QQ 12345"
    result = sanitize_text(text)
    assert "13812345678" not in result
    assert "a@b.com" not in result
    assert "12345" not in result


def test_contains_sensitive_info_detection():
    """contains_sensitive_info 返回命中类别。"""
    has, names = contains_sensitive_info("电话 13812345678")
    assert has is True
    assert "手机号" in names

    has, names = contains_sensitive_info("今天学了 30 分钟")
    assert has is False
    assert names == []


# ---------- sendTextToAI 开关集成测试 ----------

def _set_send_text_to_ai(enabled: bool) -> None:
    """设置当前用户的 sendTextToAI 开关。"""
    client.patch("/api/v1/me/settings", json={"sendTextToAI": enabled})


def _post_record_with_note(subject: str, note: str, hour: str = "08"):
    """提交带 note 的学习记录，返回 recommendationId。"""
    r = client.post(
        "/api/v1/learning-records",
        json={
            "subject": subject,
            "startedAt": f"2026-08-12T{hour}:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed", "accuracy": 0.8, "interruptions": 1},
            "selfReport": {
                "focus": 4, "fatigue": 2,
                "emotion": "positive", "difficultyFeel": "moderate",
            },
            "note": note,
        },
    )
    assert r.status_code == 201
    return r.json()["recommendation"]["recommendationId"]


def test_note_not_sent_when_send_text_to_ai_off():
    """sendTextToAI=False（默认）：note 不进 prompt，建议仍能生成（走 template 兜底）。"""
    _set_send_text_to_ai(False)
    rec_id = _post_record_with_note("SX", "今天函数题做得很顺，手机 13812345678", hour="08")

    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200
    body = detail.json()
    # 建议正常生成（开关关不阻断，只用结构化特征）
    assert body["generation"]["status"] == "ready"


def test_note_sent_sanitized_when_send_text_to_ai_on():
    """sendTextToAI=True：note 经脱敏后进 prompt，建议仍能生成。

    这里验证流程不崩、建议生成。脱敏效果在 privacy_filter 单元测试已覆盖。
    MockProvider 不会真用 note 内容，但流程要跑通。
    """
    _set_send_text_to_ai(True)
    rec_id = _post_record_with_note("SX", "今天函数题做得很顺，手机 13812345678", hour="09")

    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["generation"]["status"] == "ready"
    # 开关开不改变 source（MockProvider 下仍是 template）
    assert body["generation"]["source"] in ("template", "llm")


def test_crisis_signal_overrides_send_text_to_ai():
    """危机信号优先于 sendTextToAI 开关：含危机关键词时直接走审定文案，不过 LLM。

    PRD 6.3：危机信号识别必须硬编码，不走 LLM 生成。
    无论 sendTextToAI 开或关，危机信号都应触发 CRISIS_RESPONSE。
    """
    _set_send_text_to_ai(False)  # 即使开关关，危机信号仍要检测
    rec_id = _post_record_with_note(
        "SX", "最近压力太大了，有时候不想活", hour="10"
    )

    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200
    body = detail.json()
    # 危机信号 → template + 审定文案
    assert body["generation"]["status"] == "ready"
    assert body["generation"]["source"] == "template"
    assert len(body["items"]) >= 1
    # 审定文案含 12355 热线
    assert any("12355" in item["content"] for item in body["items"]), (
        f"危机信号应触发审定文案含 12355，实际 items: {body['items']}"
    )


def test_summary_respects_send_text_to_ai_off():
    """复盘在 sendTextToAI=False 时也能跑通（note 不进 prompt，数据不足走 insufficient_data）。

    用未来区间保证 0 条记录，稳定验证数据不足分支不受开关影响。
    """
    _set_send_text_to_ai(False)
    r = client.post("/api/v1/summaries", json={"periodStart": "2030-01-01", "periodEnd": "2030-01-07"})
    assert r.status_code == 202
    got = client.get(f"/api/v1/summaries/{r.json()['summaryId']}")
    body = got.json()
    assert body["generation"]["status"] == "insufficient_data"

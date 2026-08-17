"""
烟雾测试：覆盖关键 schema 校验 + 几个核心接口能正常返回。

不追求覆盖率，只保证：
  1. 启动后能 import 整个 app
  2. 所有 schema 用 openapi.yaml 的 example 数据能校验通过
  3. 关键接口能成功响应（包含 /health / 鉴权接口 / 列表接口）
  4. 错误响应统一格式
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from mock_data import (
    GOAL_LIST_MOCK,
    LEARNING_RECORD_LIST_MOCK,
    PLAN_LIST_MOCK,
    RECOMMENDATION_LIST_MOCK,
    STATE_RESULT_LIST_MOCK,
    SUMMARY_LIST_MOCK,
    USER_MOCK,
)
from schemas.assessment import AssessmentFeedback
from schemas.common import Error
from schemas.enums import (
    Completion,
    DifficultyFeel,
    Emotion,
    GenerationSource,
    GoalType,
    Rating,
    RecScene,
    Stage,
    StateLabel,
    Subject,
    TaskStatus,
    Trend,
)
from schemas.goal import GoalCreate, GoalUpdate
from schemas.learning_record import RecordInput
from schemas.recommendation import RecommendationCreate
from schemas.summary import SummaryCreate
from schemas.user import (
    GuardianAuthorizationRequest,
    SettingsUpdate,
    UserProfilePatch,
    UserProfilePut,
)

client = TestClient(app)


# ---------- 1. 应用可启动 ----------

def test_app_starts() -> None:
    """导入成功即说明 ORM / schema / 路由都能加载。"""
    assert app.title == "EpochX API"


def test_health_endpoint() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- 2. 枚举值无漂移（与 openapi.yaml 对齐）----------

def test_enum_values_match_openapi() -> None:
    assert {s.value for s in Subject} == {
        "chinese", "math", "english", "physics", "chemistry", "biology",
        "history", "geography", "politics", "other",
    }
    assert {s.value for s in StateLabel} == {
        "efficient_stable", "fatigue_warning", "emotion_blocked",
        "fluctuating_up", "insufficient_data",
    }
    assert {s.value for s in Stage} == {"junior", "senior"}
    assert {s.value for s in Trend} == {"up", "flat", "down"}
    assert {s.value for s in RecScene} == {"post_session", "weekly_review"}
    assert {s.value for s in GenerationSource} == {"llm", "template"}
    assert {s.value for s in Rating} == {"useful", "neutral", "not_useful"}
    assert {s.value for s in TaskStatus} == {
        "pending", "completed", "partial", "abandoned",
    }
    assert {s.value for s in Completion} == {"completed", "partial", "abandoned"}
    assert {s.value for s in DifficultyFeel} == {"easy", "moderate", "hard"}
    assert {s.value for s in Emotion} == {"positive", "neutral", "negative"}
    assert {s.value for s in GoalType} == {"short_term", "long_term"}


# ---------- 3. Mock 数据能通过 schema 校验 ----------

def test_mock_data_validates() -> None:
    """mock_data.py 里硬编码的 6 个 List 必须能通过对应 schema 校验。"""
    assert GOAL_LIST_MOCK.items[0].goal_id == "g_5501"
    assert PLAN_LIST_MOCK.items[0].plan_id == "p_9001"
    assert LEARNING_RECORD_LIST_MOCK.items[0].subject == Subject.math
    assert STATE_RESULT_LIST_MOCK.items[0].state_label == StateLabel.fatigue_warning
    assert RECOMMENDATION_LIST_MOCK.items[0].scene == RecScene.post_session
    assert SUMMARY_LIST_MOCK.items[0].summary_id == "sum_4402"


# ---------- 4. 关键 schema 的 Pydantic alias / 字段名 ----------

def test_user_response_uses_camelcase_aliases() -> None:
    """响应序列化时按 alias 输出 camelCase。"""
    data = USER_MOCK.model_dump(by_alias=True)
    assert "userId" in data
    assert "guardianAuthorization" in data
    assert "onboardingCompleted" in data
    # 下划线形式的内部字段不应出现在 JSON 里
    assert "user_id" not in data
    assert "onboarding_completed" not in data


# ---------- 5. SettingsUpdate 至少传一项的校验 ----------

def test_settings_update_requires_at_least_one_field() -> None:
    with pytest.raises(ValueError, match="至少传一项"):
        SettingsUpdate.model_validate({})

    ok = SettingsUpdate.model_validate({"sendTextToAI": True})
    assert ok.send_text_to_ai is True


# ---------- 6. GuardianAuthorizationRequest 只接邮箱 ----------


def test_guardian_request_requires_email() -> None:
    """项目目前只有邮箱注册/验证，guardianPhone 字段已移除。"""
    # 空 body：报错（guardianEmail 必填）
    with pytest.raises(ValueError, match="guardianEmail"):
        GuardianAuthorizationRequest.model_validate({})
    # 正常传邮箱：OK
    ok = GuardianAuthorizationRequest.model_validate(
        {"guardianEmail": "g@e.com"}
    )
    assert ok.guardian_email == "g@e.com"


# ---------- 7. RecordInput 字段范围 ----------

def test_record_input_rejects_bad_values() -> None:
    base = {
        "subject": "math",
        "startedAt": "2026-08-17T10:00:00+08:00",
        "durationMinutes": 30,
        "behavior": {"completion": "completed"},
        "selfReport": {
            "focus": 5, "fatigue": 2,
            "emotion": "positive", "difficultyFeel": "easy",
        },
    }
    # 正常
    r = RecordInput.model_validate(base)
    assert r.subject == Subject.math
    # focus=0 越界
    bad = {**base, "selfReport": {**base["selfReport"], "focus": 0}}
    with pytest.raises(ValueError):
        RecordInput.model_validate(bad)
    # duration=0 越界
    bad = {**base, "durationMinutes": 0}
    with pytest.raises(ValueError):
        RecordInput.model_validate(bad)


# ---------- 8. 接口能响应（鉴权跳过，current_user 永远返回 mock）----------

def test_get_me() -> None:
    r = client.get("/me")
    assert r.status_code == 200
    body = r.json()
    assert body["userId"] == "u_10237"
    assert body["guardianAuthorization"]["status"] == "active"


def test_list_goals_uses_camelcase_pagination() -> None:
    r = client.get("/goals")
    assert r.status_code == 200
    body = r.json()
    assert "pagination" in body
    # 驼峰输出
    assert "pageSize" in body["pagination"]
    assert "page_size" not in body["pagination"]


def test_create_learning_record_validation() -> None:
    """POST /learning-records 走完整 Pydantic 校验，response camelCase。"""
    payload = {
        "subject": "math",
        "startedAt": "2026-08-17T10:00:00+08:00",
        "durationMinutes": 30,
        "behavior": {
            "completion": "completed", "accuracy": 0.85,
            "interruptions": 0, "blurCount": 1,
        },
        "selfReport": {
            "focus": 5, "fatigue": 2,
            "emotion": "positive", "difficultyFeel": "easy",
        },
    }
    r = client.post("/learning-records", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["subject"] == "math"
    assert "assessment" in body
    assert "recommendation" in body
    # 驼峰
    assert "blurCount" in body["behavior"]
    assert "recommendationId" in body["recommendation"]


def test_settings_update_validation_at_route() -> None:
    """PATCH /me/settings 空 body 应被 Pydantic 拒掉并返回 400 + 统一格式。"""
    r = client.patch("/me/settings", json={})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_guardian_request_validation_at_route() -> None:
    """POST /me/guardian-authorization 空 body 应被拒。"""
    r = client.post("/me/guardian-authorization", json={})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_error_response_uses_unified_format() -> None:
    """所有非 2xx 都返回 { error: { code, message, field? } }。"""
    r = client.patch("/me/settings", json={})
    body = r.json()
    Error.model_validate(body)  # 强校验：必须能解析为 Error schema


# ---------- 9. 列表接口都带 items + pagination（camelCase）----------

@pytest.mark.parametrize(
    "path",
    [
        "/goals",
        "/plans",
        "/learning-records",
        "/recommendations",
        "/summaries",
    ],
)
def test_list_endpoints_have_pagination(path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}"
    body = r.json()
    assert "items" in body
    assert "pagination" in body
    assert "pageSize" in body["pagination"]


def test_assessments_returns_history_not_list() -> None:
    """GET /assessments 返回单学科历史（subject + items），不是分页列表。"""
    r = client.get("/assessments?subject=math")
    assert r.status_code == 200
    body = r.json()
    assert "subject" in body
    assert "items" in body
    assert "pagination" not in body

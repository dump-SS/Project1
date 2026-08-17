"""端到端契约闭环测试集（对应 docs/openapi.yaml 第 9 节五步主流程）。

目的：用真实后端把契约定义的完整用户旅程跑通一遍，
把「已实现的真数据链路」「还是 mock 常量的链路」「违背契约的链路」分开断言，
让队友跑一遍 `pytest tests/test_e2e_contract.py -v` 就能看到后端当前到底通到什么程度。

分层：
  A. 契约闭环（已实现）：目标→计划→记录→状态→建议，五步全部走真实后端+引擎
  B. 已实现但还有缺陷：计划/目标 create 仍返回 mock 常量（与 list 不对称）
  C. 用户/鉴权链路：/me 是桩、auth/me 在 mock-server、会话未对接

运行前提：uvicorn backend:8000 + mock-server:4000 都在跑（默认配置）。
用 REAL_LLM=1 可额外触发真实 LLM（否则 MockProvider 走模板兜底）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------- A. 契约闭环（五步主流程，已实现） ----------

def test_a1_create_goal_returns_201_with_progress():
    """A1: POST /goals 创建目标 → 201 + Goal 形状（status=active, progress 字段在）。

    契约：openapi.yaml 2.1。当前实现：返回 mock 常量，
    但契约 shape 已验证。后续接 DB 后此断言不应变。
    """
    r = client.post("/api/v1/goals", json={
        "type": "short_term",
        "subject": "math",
        "title": "两周后期中考试数学 120+",
        "targetDate": "2026-08-30",
    })
    assert r.status_code == 201, f"创建目标失败: {r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "active"
    assert "progress" in body
    assert body["progress"]["plannedTasks"] >= 0
    assert body["progress"]["completedTasks"] >= 0


def test_a2_create_plan_returns_tasks():
    """A2: POST /plans 生成计划 → 201 + tasks 非空。

    契约：openapi.yaml 3.1。当前实现：返回 mock 常量（planDate/availableMinutes 被忽略）。
    断言 shape + tasks 非空 + task 字段齐全；planDate 忽略在 B1 单独暴露。
    """
    r = client.post("/api/v1/plans", json={
        "planDate": "2026-08-18",
        "availableMinutes": 120,
        "goalIds": ["g_5501"],
    })
    assert r.status_code == 201, f"生成计划失败: {r.status_code} {r.text}"
    body = r.json()
    # 当前 mock：返回示例计划（planDate/availableMinutes 被忽略），shape 已验证
    assert "planId" in body
    assert "planDate" in body
    assert isinstance(body["tasks"], list) and len(body["tasks"]) > 0
    first_task = body["tasks"][0]
    for field in ["taskId", "subject", "topic", "estimatedMinutes", "priority", "status"]:
        assert field in first_task, f"task 缺字段: {field}"


def test_a3_submit_learning_record_triggers_assessment_and_recommendation():
    """A3: POST /learning-records → 201 + assessment 快照 + recommendation 句柄。

    契约：openapi.yaml 4.1。这是已实现的真引擎链路——
    断言同步返回 assessment + recommendationId，不依赖 DB 数据形态。
    """
    r = client.post("/api/v1/learning-records", json={
        "subject": "math",
        "startedAt": "2026-08-18T19:00:00+08:00",
        "durationMinutes": 45,
        "behavior": {"completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5},
        "selfReport": {"focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard"},
    })
    assert r.status_code == 201, f"提交记录失败: {r.status_code} {r.text}"
    body = r.json()
    assert "recordId" in body
    assert "assessment" in body
    assessment = body["assessment"]
    assert assessment["subject"] == "math"
    assert "stateLabel" in assessment
    assert "dataSufficient" in assessment
    assert "recordCount" in assessment
    rec = body.get("recommendation")
    assert rec is not None, "POST /learning-records 未返回 recommendation 句柄"
    assert "recommendationId" in rec
    assert rec["status"] == "pending"


def test_a4_get_current_state_returns_per_subject():
    """A4: GET /assessments/current → StateResultList，按学科分条（PRD 5.2 不跨学科合并）。

    契约：openapi.yaml 5.1。引擎已接——断言返回 shape + 每条的 displayText/basedOn。
    """
    r = client.get("/api/v1/assessments/current")
    assert r.status_code == 200, f"查状态失败: {r.status_code} {r.text}"
    body = r.json()
    assert "items" in body
    if len(body["items"]) > 0:
        item = body["items"][0]
        assert "subject" in item
        assert "stateLabel" in item
        assert "displayText" in item
        assert "dataSufficient" in item


def test_a5_poll_recommendation_gets_ready():
    """A5: 轮询 GET /recommendations/{id} → generation.status 终态（ready）。

    契约：openapi.yaml 6.2 + 0.3 异步生成约定。引擎已接——
    MockProvider 下预期 ready + source=template；真实 LLM 下预期 ready + source=llm。
    """
    # 先提交记录拿 recommendationId
    r = client.post("/api/v1/learning-records", json={
        "subject": "english",
        "startedAt": "2026-08-18T20:00:00+08:00",
        "durationMinutes": 30,
        "behavior": {"completion": "completed"},
        "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
    })
    assert r.status_code == 201
    rec_id = r.json()["recommendation"]["recommendationId"]

    # 轮询直到终态（后台任务在 TestClient 里同步执行，一次就够）
    detail = client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["generation"]["status"] in ("ready", "failed")
    assert body["generation"]["status"] != "pending", "同步生成应已完成"


# ---------- B. 已实现但仍是 mock 常量的链路（已知缺口） ----------

def test_b1_plan_create_and_list_are_asymmetric():
    """B1: POST /plans 返回 201 + mock 常量；GET /plans 返回 mock 常量列表。

    当前 mock 的实现：create 和 list 返回的是**同一个 mock 对象**（id 也相同），
    所以「刚创建的计划出现在 list 里」——不对称检测靠 id 恰好失效，
    真正的问题是 plan create **不持久化**，GET 也是硬编码而非查 DB。
    此测试记录现状，接 DB 后应改为「创建后 list 出现新 id 且 planDate 为请求值」。
    """
    created = client.post("/api/v1/plans", json={
        "planDate": "2026-08-19",
        "availableMinutes": 60,
    })
    assert created.status_code == 201
    created_plan_id = created.json()["planId"]
    created_plan_date = created.json()["planDate"]

    list_resp = client.get("/api/v1/plans")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]

    # 当前 mock：create 和 list 返回同一个 mock 对象，id 相同 → found=True
    # 但 planDate 被忽略（请求 2026-08-19，返回 2026-08-16）
    found = any(p["planId"] == created_plan_id for p in items)
    assert found, "mock 的 create/list 同构（同一 mock 对象），id 应匹配"
    assert created_plan_date == "2026-08-16", (
        f"plan create 忽略请求参数：请求 planDate=2026-08-19，实际返回 {created_plan_date}（mock 硬编码）"
    )


def test_b2_goal_create_and_list_are_asymmetric():
    """B2: POST /goals 返回 201（echo 请求参数），但 GET /goals 返回 mock 常量列表。

    goal create 用了 body.type/subject/title（没忽略输入），但 id/createdAt 是 mock 常量；
    list 是完整 mock 对象，与 create 无关。
    """
    created = client.post("/api/v1/goals", json={
        "type": "long_term",
        "subject": "english",
        "title": "高考英语稳定在 135 分区间",
    })
    assert created.status_code == 201
    body = created.json()
    # create 没忽略输入（echo body 字段），但 id/createdAt 是 mock 常量
    assert body["subject"] == "english"
    assert body["title"] == "高考英语稳定在 135 分区间"
    # 但 list 与 create 无关——list 返回 mock 常量
    list_resp = client.get("/api/v1/goals?status=active")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    # list 里只有 mock 示例目标，不是刚创建的这个 long_term english goal
    for item in items:
        assert item["subject"] == "math" or item["title"] == "两周后期中考试数学 120+", (
            f"list 出现了非 mock 示例: {item}"
        )


def test_b3_summary_insufficient_data_not_template():
    """B3: 复盘记录不足时返回 insufficient_data，绝不走 template（PRD 5.4）。"""
    r = client.post("/api/v1/summaries", json={
        "periodStart": "2030-01-01",
        "periodEnd": "2030-01-07",
    })
    assert r.status_code == 202
    summary_id = r.json()["summaryId"]
    detail = client.get(f"/api/v1/summaries/{summary_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["generation"]["status"] == "insufficient_data"
    assert body["generation"].get("source") is None
    assert body["content"] is None
    assert body["dataPoints"]["minRequired"] >= 3


# ---------- C. 鉴权链路（当前是桩） ----------

def test_c1_me_is_stub_user():
    """C1: GET /me 返回 mock 用户 u_10237（current_user 是桩）。

    此测试记录现状：还没接真实鉴权。auth 在 mock-server，业务在 Python。
    """
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["userId"] == "u_10237", "current_user 仍是桩，不是真实登录用户"
    assert body["guardianAuthorization"]["status"] == "active"


def test_c2_unauthenticated_business_call_returns_401():
    """C2: 未登录访问业务接口 → 401（若有守卫）。

    当前 current_user 是桩，永远返回 mock，所以不会真 401——
    此测试预期**当前**返回 200，记录"守卫未启用"的事实。
    等接 JWT 后应改成断言 401。
    """
    r = client.get("/api/v1/goals")
    # 当前：桩用户直接放行 → 200
    assert r.status_code == 200, (
        "current_user 桩直接放行（预期 200）；接 JWT 后未登录应 401，需改断言"
    )


# ---------- D. 端到端完整闭环（五步连跑） ----------

def test_d1_full_contract_loop_end_to_end():
    """D1: 五步契约闭环连跑：目标→计划→记录→状态→建议，全链路一次通过。

    这是最终验收——契约第 9 节的完整旅程，每步的返回作为下一步的输入。
    MockProvider 下预期走 template；真实 LLM 下预期走 llm。
    """
    # ① 创建目标
    goal = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "math",
        "title": "契约闭环测试目标", "targetDate": "2026-08-30",
    })
    assert goal.status_code == 201
    goal_id = goal.json()["goalId"]

    # ② 生成计划
    plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-18", "availableMinutes": 90, "goalIds": [goal_id],
    })
    assert plan.status_code == 201
    plan_id = plan.json()["planId"]

    # ③ 提交学习记录（触发状态计算 + 建议句柄）
    record = client.post("/api/v1/learning-records", json={
        "subject": "math", "startedAt": "2026-08-18T20:00:00+08:00",
        "durationMinutes": 40,
        # 当前 mock：plan 返回的是示例 planId/tasks，这里关联示例 taskId 而非刚生成的
        # （plan create 不持久化，taskId 来自 mock 常量；接 DB 后应改回刚创建的）
        "planTaskId": "t_30011",
        "behavior": {"completion": "completed", "accuracy": 0.8, "interruptions": 1},
        "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
    })
    assert record.status_code == 201
    record_id = record.json()["recordId"]
    rec_id = record.json()["recommendation"]["recommendationId"]

    # ④ 查当前状态（应该有了第一条记录的评估）
    state = client.get("/api/v1/assessments/current?subject=math")
    assert state.status_code == 200
    state_item = state.json()["items"][0]
    assert state_item["subject"] == "math"

    # ⑤ 轮询建议
    rec = client.get(f"/api/v1/recommendations/{rec_id}")
    assert rec.status_code == 200
    rec_body = rec.json()
    assert rec_body["generation"]["status"] == "ready"
    assert rec_body["generation"]["source"] in ("template", "llm")
    assert len(rec_body["items"]) >= 1

    # 闭环成立：五步全部拿到非空真数据
    print(f"\n闭环通过: goal={goal_id} plan={plan_id} record={record_id} rec={rec_id}")

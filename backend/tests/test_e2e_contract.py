"""端到端契约闭环测试集（对应 docs/openapi.yaml 第 9 节五步主流程）。

目的：用真实后端把契约定义的完整用户旅程跑通一遍，
把「已实现的真数据链路」「还是 mock 常量的链路」「违背契约的链路」分开断言，
让队友跑一遍 `pytest tests/test_e2e_contract.py -v` 就能看到后端当前到底通到什么程度。

分层：
  A. 契约闭环（已实现）：目标→计划→记录→状态→建议，五步全部走真实后端+引擎
  B. 计划/目标 CRUD 真实现（已接 DB）：create 落库、list 一致、409/regenerate、PATCH、归档、属主隔离、404
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

    契约：openapi.yaml 2.1。已接 DB：create 真落库，progress 初始为 0。
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

    契约：openapi.yaml 3.1。已接 DB：planDate/availableMinutes 来自请求，
    按 active 目标生成任务列表。先建目标再建计划，保证 tasks 非空。
    """
    # 先建一个 active 目标，保证计划能生成任务
    client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "math", "title": "A2 数学目标",
    })
    r = client.post("/api/v1/plans", json={
        "planDate": "2026-08-18",
        "availableMinutes": 120,
    })
    assert r.status_code == 201, f"生成计划失败: {r.status_code} {r.text}"
    body = r.json()
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


# ---------- B. 计划/目标 CRUD 真实现（已接 DB） ----------

def test_b1_plan_create_persists_and_appears_in_list():
    """B1: POST /plans 落库后，GET /plans 列表里能查到刚创建的计划。

    之前的 bug：create 返回 mock 常量、不落库，list 也返 mock 常量，
    create 返回的 planId 在 list 里只是恰好同 id（同一个 mock 对象）。
    修复后：create 真落库，list 真读库，planDate 为请求值而非硬编码。
    """
    created = client.post("/api/v1/plans", json={
        "planDate": "2026-08-19",
        "availableMinutes": 60,
    })
    assert created.status_code == 201
    created_plan_id = created.json()["planId"]
    created_plan_date = created.json()["planDate"]
    # 修复后：planDate 是请求值，不再是 mock 硬编码的 2026-08-16
    assert created_plan_date == "2026-08-19", (
        f"plan create 应使用请求 planDate，实际返回 {created_plan_date}"
    )

    list_resp = client.get("/api/v1/plans")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    # 修复后：刚创建的 planId 真出现在 list 里（落库一致）
    found = any(p["planId"] == created_plan_id for p in items)
    assert found, "create 落库后，list 应能查到刚创建的计划"


def test_b2_goal_create_persists_and_appears_in_list():
    """B2: POST /goals 落库后，GET /goals 列表里能查到刚创建的目标。

    之前的 bug：create echo 输入但 id/createdAt 是 mock 常量、不落库；
    list 返 mock 常量，与 create 完全脱节。
    修复后：create 真落库，list 真读库，刚创建的目标出现在 list 里。
    """
    created = client.post("/api/v1/goals", json={
        "type": "long_term",
        "subject": "english",
        "title": "高考英语稳定在 135 分区间",
    })
    assert created.status_code == 201
    body = created.json()
    created_id = body["goalId"]
    assert body["subject"] == "english"
    assert body["title"] == "高考英语稳定在 135 分区间"

    list_resp = client.get("/api/v1/goals?status=all")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    # 修复后：刚创建的 goalId 真出现在 list 里
    found = any(g["goalId"] == created_id for g in items)
    assert found, "create 落库后，list 应能查到刚创建的目标"


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


def test_b4_plan_create_409_on_duplicate_plandate():
    """B4: 同一 planDate 重复创建 → 409 STATE_CONFLICT（契约 3.1）。"""
    payload = {"planDate": "2026-08-20", "availableMinutes": 60}
    first = client.post("/api/v1/plans", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/plans", json=payload)
    assert second.status_code == 409, f"重复 planDate 应 409，实际 {second.status_code}"
    err = second.json()["error"]
    assert err["code"] == "STATE_CONFLICT"


def test_b5_plan_regenerate_overrides_existing():
    """B5: regenerate=true 覆盖当日已有计划（契约 3.1）。

    旧 planId 应从 list 中消失（CASCADE 删除），新 planId 出现。
    """
    payload = {"planDate": "2026-08-21", "availableMinutes": 60}
    first = client.post("/api/v1/plans", json=payload)
    assert first.status_code == 201
    old_plan_id = first.json()["planId"]

    override = client.post("/api/v1/plans", json={**payload, "regenerate": True})
    assert override.status_code == 201
    new_plan_id = override.json()["planId"]
    assert new_plan_id != old_plan_id, "regenerate 应生成新 planId"

    # 旧 planId 在 list 中应已不存在
    items = client.get("/api/v1/plans").json()["items"]
    ids = {p["planId"] for p in items}
    assert old_plan_id not in ids, "regenerate 后旧计划应被删除"
    assert new_plan_id in ids


def test_b6_plan_get_404_on_missing_id():
    """B6: GET /plans/{不存在的 id} → 404（契约 3.2）。

    之前的 bug：任意 id 都返回 200 + mock 常量。
    """
    r = client.get("/api/v1/plans/p_does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_b7_patch_plan_task_marks_completed_and_user_adjusted():
    """B7: PATCH /plans/{id}/tasks/{taskId} → status=completed + userAdjusted=true（契约 3.3）。

    之前的 bug：PATCH 返 mock 常量，不落库。
    """
    # 先建目标 + 计划拿真实 taskId
    goal = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "physics", "title": "B7 物理目标",
    })
    goal_id = goal.json()["goalId"]
    plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-22", "availableMinutes": 60, "goalIds": [goal_id],
    })
    task_id = plan.json()["tasks"][0]["taskId"]
    plan_id = plan.json()["planId"]

    r = client.patch(
        f"/api/v1/plans/{plan_id}/tasks/{task_id}",
        json={"status": "completed"},
    )
    assert r.status_code == 200, f"PATCH 失败: {r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "completed"
    assert body["userAdjusted"] is True
    assert body["taskId"] == task_id

    # 再查计划详情，确认落库
    detail = client.get(f"/api/v1/plans/{plan_id}").json()
    task = next(t for t in detail["tasks"] if t["taskId"] == task_id)
    assert task["status"] == "completed"


def test_b8_patch_plan_task_soft_delete():
    """B8: PATCH removed=true 软删除任务，GET 计划详情不再列出该任务。"""
    goal = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "chemistry", "title": "B8 化学目标",
    })
    plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-23", "availableMinutes": 90, "goalIds": [goal.json()["goalId"]],
    })
    plan_id = plan.json()["planId"]
    task_id = plan.json()["tasks"][0]["taskId"]

    r = client.patch(
        f"/api/v1/plans/{plan_id}/tasks/{task_id}",
        json={"removed": True},
    )
    assert r.status_code == 200
    assert r.json()["removed"] is True

    # 计划详情不再列出该任务（_load_plan_tasks 过滤 removed=True）
    detail = client.get(f"/api/v1/plans/{plan_id}").json()
    ids = {t["taskId"] for t in detail["tasks"]}
    assert task_id not in ids, "软删除的任务不应出现在计划详情"


def test_b9_goal_archive_via_patch_status():
    """B9: PATCH /goals/{id} status=archived 归档，list 默认 active 查不到（契约 2.3 归档代替删除）。"""
    created = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "biology", "title": "B9 生物目标",
    })
    goal_id = created.json()["goalId"]

    r = client.patch(f"/api/v1/goals/{goal_id}", json={"status": "archived"})
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    # 默认 status=active 查不到，status=all 能查到
    active_items = client.get("/api/v1/goals").json()["items"]
    assert all(g["goalId"] != goal_id for g in active_items), "归档目标不应出现在 active 列表"
    all_items = client.get("/api/v1/goals?status=all").json()["items"]
    assert any(g["goalId"] == goal_id for g in all_items), "归档目标应在 status=all 列表"


def test_b10_goal_patch_404_on_missing_id():
    """B10: PATCH /goals/{不存在} → 404（之前返 mock 常量）。"""
    r = client.patch("/api/v1/goals/g_does_not_exist", json={"title": "x"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_b11_goal_patch_rejects_invalid_status():
    """B11: PATCH /goals/{id} status=completed → 400（契约仅允许 active/archived）。"""
    created = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "history", "title": "B11 历史目标",
    })
    goal_id = created.json()["goalId"]
    r = client.patch(f"/api/v1/goals/{goal_id}", json={"status": "completed"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert r.json()["error"]["field"] == "status"


def test_b12_goal_progress_aggregates_from_plan_tasks():
    """B12: 目标进度（plannedTasks/completedTasks/ratio）从 plan_tasks 表实时聚合。

    建目标 → 建计划（生成任务）→ 完成一个任务 → 查目标列表，progress 应反映完成情况。
    """
    goal = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "geography", "title": "B12 地理目标",
    })
    goal_id = goal.json()["goalId"]

    plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-24", "availableMinutes": 90, "goalIds": [goal_id],
    })
    plan_id = plan.json()["planId"]
    tasks = plan.json()["tasks"]
    assert len(tasks) >= 1, "应有任务生成"

    # 完成第一个任务
    client.patch(
        f"/api/v1/plans/{plan_id}/tasks/{tasks[0]['taskId']}",
        json={"status": "completed"},
    )

    # 查目标列表，进度应反映
    items = client.get("/api/v1/goals?status=all").json()["items"]
    target = next(g for g in items if g["goalId"] == goal_id)
    assert target["progress"]["plannedTasks"] == len(tasks), (
        f"plannedTasks 应 = 任务数 {len(tasks)}，实际 {target['progress']['plannedTasks']}"
    )
    assert target["progress"]["completedTasks"] == 1
    assert target["progress"]["ratio"] > 0


def test_b13_goal_user_isolation():
    """B13: 不同用户的 goal 互不可见（属主校验）。

    用户 A 创建的目标，用户 B 查 list 看不到，PATCH 也 404。
    """
    # 用户 A 创建
    a_created = client.post("/api/v1/goals", json={
        "type": "short_term", "subject": "politics", "title": "B13 A 的目标",
    }, headers={"X-User-ID": "user_a"})
    assert a_created.status_code == 201
    a_goal_id = a_created.json()["goalId"]

    # 用户 B 查 list 看不到
    b_list = client.get("/api/v1/goals?status=all", headers={"X-User-ID": "user_b"}).json()
    assert all(g["goalId"] != a_goal_id for g in b_list["items"]), "用户 B 不应看到 A 的目标"

    # 用户 B PATCH A 的目标 → 404
    b_patch = client.patch(
        f"/api/v1/goals/{a_goal_id}",
        json={"title": "B 改 A 的"},
        headers={"X-User-ID": "user_b"},
    )
    assert b_patch.status_code == 404, "跨用户 PATCH 应 404"


def test_b14_plan_user_isolation():
    """B14: 不同用户的 plan 互不可见（属主校验）。

    用户 A 创建的计划，用户 B GET 该 planId → 404。
    """
    a_plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-25", "availableMinutes": 60,
    }, headers={"X-User-ID": "user_a"})
    assert a_plan.status_code == 201
    a_plan_id = a_plan.json()["planId"]

    b_get = client.get(f"/api/v1/plans/{a_plan_id}", headers={"X-User-ID": "user_b"})
    assert b_get.status_code == 404, "跨用户 GET 计划应 404"


def test_b15_plan_adapted_from_null_for_new_user():
    """B15: 新用户无历史评估数据 → adaptedFrom=null（契约允许）。

    PRD 5.1：新用户走规则模板，无 adaptedFrom。
    """
    r = client.post("/api/v1/plans", json={
        "planDate": "2026-08-26", "availableMinutes": 60,
    }, headers={"X-User-ID": "user_b15_new"})
    assert r.status_code == 201
    assert r.json()["adaptedFrom"] is None, "新用户 adaptedFrom 应为 null"


def test_b16_plan_cold_start_has_fallback_task():
    """B16: 无目标用户建计划 → tasks 至少 1 条兜底任务（Jacky 方案A P0-1）。

    冷启动场景：新用户、无学科、无目标、无历史记录。
    _split_tasks 返回空时，兜底补一条通用任务，保证前端推荐有内容可填。
    """
    r = client.post("/api/v1/plans", json={
        "planDate": "2026-08-27", "availableMinutes": 30,
    }, headers={"X-User-ID": "user_b16_cold"})
    assert r.status_code == 201
    body = r.json()
    # P0-1：tasks 至少 1 条
    assert len(body["tasks"]) >= 1, "冷启动应兜底至少 1 条任务"
    task = body["tasks"][0]
    # P0-3：subject 是合法 Subject 枚举
    assert task["subject"] in (
        "chinese", "math", "english", "physics", "chemistry",
        "biology", "history", "geography", "politics", "other",
    ), f"task.subject 非法: {task['subject']}"
    # P0-2：topic 是可读中文（非空、非裸 enum）
    assert task["topic"], "task.topic 不应为空"
    assert task["topic"] != task["subject"], "task.topic 不应等于裸 subject 枚举"


# ---------- C. 鉴权链路（当前是桩） ----------

def test_c1_me_returns_real_orm_data():
    """C1: GET /me 返回 ORM 真实资料（已接 DB，不再返 mock 常量）。

    未建档用户：onboardingCompleted=false，guardian 状态 pending。
    userId 仍是 u_10237（无登录态回落，auth 在 mock-server）。
    """
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["userId"] == "u_10237"
    # 未建档：onboarding 未完成，guardian 未授权
    assert body["onboardingCompleted"] is False
    assert body["guardianAuthorization"]["status"] == "pending"


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

    # ② 生成计划（接 DB 后，plan 返回真实 taskId）
    plan = client.post("/api/v1/plans", json={
        "planDate": "2026-08-27", "availableMinutes": 90, "goalIds": [goal_id],
    })
    assert plan.status_code == 201
    plan_id = plan.json()["planId"]
    plan_task_id = plan.json()["tasks"][0]["taskId"]

    # ③ 提交学习记录（触发状态计算 + 建议句柄），关联真实 planTaskId
    record = client.post("/api/v1/learning-records", json={
        "subject": "math", "startedAt": "2026-08-18T20:00:00+08:00",
        "durationMinutes": 40,
        "planTaskId": plan_task_id,
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


# ---------- E. Assessment Feedback 落库 ----------

def test_e1_assessment_feedback_persists_and_overwrites():
    """E1: PUT /assessments/{id}/feedback → 204，反馈落库且可幂等覆盖。

    契约：openapi.yaml 5.3。一条评估至多一份反馈，PUT 幂等覆盖。
    修复前：接口仅受理不落库（TODO）；修复后：feedback_accurate + feedback_submitted_at 落库。
    """
    # 提交足够记录让 data_sufficient=true（窗口默认 7 条）
    for i in range(7):
        client.post("/api/v1/learning-records", json={
            "subject": "math",
            "startedAt": f"2026-08-1{i+1}T19:00:00+08:00",
            "durationMinutes": 45,
            "behavior": {"completion": "completed", "accuracy": 0.8, "interruptions": 1},
            "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
        })

    # 拿到 data_sufficient 的 assessmentId（GET /assessments/current 返回最新快照 id）
    state = client.get("/api/v1/assessments/current?subject=math").json()
    assessment_id = state["items"][0].get("assessmentId")
    assert assessment_id, "7 条记录后应有 data_sufficient 的 assessmentId"

    # 提交反馈 accurate=true → 204
    r = client.put(f"/api/v1/assessments/{assessment_id}/feedback", json={"accurate": True})
    assert r.status_code == 204, f"反馈提交失败: {r.status_code} {r.text}"

    # 验证落库：直接查 ORM
    from database import SessionLocal
    from models.assessment import AssessmentSnapshot
    db = SessionLocal()
    try:
        row = db.get(AssessmentSnapshot, assessment_id)
        assert row is not None
        assert row.feedback_accurate is True
        assert row.feedback_submitted_at is not None
    finally:
        db.close()

    # 幂等覆盖：改为 accurate=false → 204，落库值更新
    r = client.put(f"/api/v1/assessments/{assessment_id}/feedback", json={"accurate": False})
    assert r.status_code == 204
    db = SessionLocal()
    try:
        row = db.get(AssessmentSnapshot, assessment_id)
        assert row.feedback_accurate is False, "幂等覆盖后应为 False"
    finally:
        db.close()


def test_e2_assessment_feedback_404_for_nonexistent():
    """E2: PUT /assessments/{不存在的id}/feedback → 404 RESOURCE_NOT_FOUND。"""
    r = client.put("/api/v1/assessments/as_nonexistent/feedback", json={"accurate": True})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_e3_assessment_feedback_user_isolation():
    """E3: 用户 B 对用户 A 的评估提交反馈 → 404（属主校验）。

    属主不匹配时返回 404 而非 403，避免泄露资源存在性（与 recommendation 一致）。
    """
    # 用户 A 提交记录生成评估
    for i in range(7):
        client.post("/api/v1/learning-records", json={
            "subject": "physics",
            "startedAt": f"2026-08-1{i+1}T19:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {"completion": "completed"},
            "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
        }, headers={"X-User-ID": "user_e3_a"})
    state = client.get("/api/v1/assessments/current?subject=physics", headers={"X-User-ID": "user_e3_a"}).json()
    assessment_id = state["items"][0].get("assessmentId")
    assert assessment_id, "用户 A 应有评估"

    # 用户 B 对 A 的评估反馈 → 404
    r = client.put(
        f"/api/v1/assessments/{assessment_id}/feedback",
        json={"accurate": True},
        headers={"X-User-ID": "user_e3_b"},
    )
    assert r.status_code == 404, "跨用户反馈应 404"

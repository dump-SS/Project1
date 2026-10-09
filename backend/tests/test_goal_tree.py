"""目标父子树测试（D6 / D29）。

覆盖：parentGoalId 读写、顶层提升（显式 null）、成环拒绝、自引用拒绝、
跨用户父目标拒绝、父目标不可见时的行为。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

HDR = {"X-User-ID": "u_test_tree"}
HDR_B = {"X-User-ID": "u_test_tree_other"}


def _mk(title: str, headers=HDR, **over):
    body = {"type": "long_term", "subject": "SX", "title": title}
    body.update(over)
    return client.post("/api/v1/goals", json=body, headers=headers)


def test_create_child_goal():
    parent_id = _mk("期末数学进前 10").json()["goalId"]
    child = _mk("本周补完函数单调性", type="short_term", parentGoalId=parent_id)
    assert child.status_code == 201
    assert child.json()["parentGoalId"] == parent_id


def test_top_level_goal_has_null_parent():
    assert _mk("顶层目标").json()["parentGoalId"] is None


def test_promote_child_to_top_level():
    """显式传 parentGoalId=null 表示提升为顶层；不传才是「不动」。"""
    parent_id = _mk("父目标").json()["goalId"]
    child_id = _mk("子目标", type="short_term", parentGoalId=parent_id).json()["goalId"]

    # 不传 → 保持
    r = client.patch(f"/api/v1/goals/{child_id}", json={"title": "子目标改名"}, headers=HDR)
    assert r.json()["parentGoalId"] == parent_id

    # 显式 null → 提升为顶层
    r = client.patch(f"/api/v1/goals/{child_id}", json={"parentGoalId": None}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["parentGoalId"] is None


def test_reject_self_as_parent():
    goal_id = _mk("自己当自己的爹").json()["goalId"]
    r = client.patch(f"/api/v1/goals/{goal_id}", json={"parentGoalId": goal_id}, headers=HDR)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "parentGoalId"


def test_reject_cycle():
    """A 的父是 B、再把 B 的父设成 A → 必须拒绝，否则沿父链上溯会死循环。"""
    a = _mk("A", type="short_term").json()["goalId"]
    b = _mk("B", type="short_term", parentGoalId=a).json()["goalId"]

    r = client.patch(f"/api/v1/goals/{a}", json={"parentGoalId": b}, headers=HDR)
    assert r.status_code == 400
    assert "环" in r.json()["error"]["message"]


def test_reject_unknown_parent():
    r = _mk("孤儿", type="short_term", parentGoalId="g_nope")
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "parentGoalId"


def test_reject_other_users_parent():
    parent_id = _mk("别人的父目标").json()["goalId"]
    r = _mk("挂到别人树下", type="short_term", parentGoalId=parent_id, headers=HDR_B)
    assert r.status_code == 400

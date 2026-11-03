"""带画像条目（D10）路由测试（契约 v1.15.0）。

覆盖：
- GET /me/profile/{group}：空组返回 []，有数据返回列表
- GET /me/profile/{group}/{key}：存在返回条目，不存在 404
- PUT /me/profile/{group}/{key}：幂等建档/更新，不重复建档
- PATCH /me/profile/{group}/{key}：局部更新，不存在 404
- DELETE /me/profile/{group}/{key}：删除返回 204，幂等
- 库层：同一 (user_id, group, key) 只保留一条（UniqueConstraint）

conftest 的 _reset_db 会在每个测试前清空所有表，故测试之间相互隔离。
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

U = "u_10237"


def _hdr(user_id: str = U) -> dict:
    return {"X-User-ID": user_id}


def _put_entry(group: str, key: str, value: str, user_id: str = U):
    return client.put(
        f"/api/v1/me/profile/{group}/{key}",
        json={"value": value},
        headers=_hdr(user_id),
    )


# ------------------------------------------------------------------ GET group


def test_get_profile_group_empty():
    r = client.get(f"/api/v1/me/profile/learning", headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


def test_get_profile_group_returns_items():
    _put_entry("learning", "weak_point", "函数/单调性")
    _put_entry("learning", "habit", "早起")
    r = client.get(f"/api/v1/me/profile/learning", headers=_hdr())
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    keys = {i["key"] for i in items}
    assert keys == {"weak_point", "habit"}
    for i in items:
        assert i["group"] == "learning"
        assert i["entryId"]
        assert i["updatedAt"]


# ------------------------------------------------------------------ GET entry


def test_get_profile_entry():
    _put_entry("state", "focus", "高")
    r = client.get(f"/api/v1/me/profile/state/focus", headers=_hdr())
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["entryId"]
    assert e["group"] == "state"
    assert e["key"] == "focus"
    assert e["value"] == "高"


def test_get_profile_entry_not_found():
    r = client.get(f"/api/v1/me/profile/learning/nonexistent", headers=_hdr())
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ PUT（幂等建档/更新）


def test_put_create_then_update():
    r1 = _put_entry("interest", "music", "古典")
    assert r1.status_code == 200, r1.text
    assert r1.json()["value"] == "古典"
    assert r1.json()["source"] == "explicit"

    # 再 PUT 同一 key，应覆盖（不重复建档）
    r2 = _put_entry("interest", "music", "爵士")
    assert r2.status_code == 200, r2.text
    assert r2.json()["value"] == "爵士"

    # 库里只有 1 行
    from database import SessionLocal
    from models.chat import UserProfile as ProfileORM

    db = SessionLocal()
    try:
        n = (
            db.query(ProfileORM)
            .filter(
                ProfileORM.user_id == U,
                ProfileORM.profile_group == "interest",
                ProfileORM.key == "music",
            )
            .count()
        )
        assert n == 1, n
    finally:
        db.close()


# ------------------------------------------------------------------ PATCH


def test_patch_profile_entry():
    _put_entry("learning", "habit", "早起")
    r = client.patch(
        f"/api/v1/me/profile/learning/habit",
        json={"value": "早睡早起"},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "早睡早起"


def test_patch_profile_entry_not_found():
    r = client.patch(
        f"/api/v1/me/profile/learning/nope",
        json={"value": "x"},
        headers=_hdr(),
    )
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ DELETE


def test_delete_profile_entry():
    _put_entry("state", "temp", "临时")
    r = client.delete(f"/api/v1/me/profile/state/temp", headers=_hdr())
    assert r.status_code == 204, r.text

    # 再 GET 应 404
    r = client.get(f"/api/v1/me/profile/state/temp", headers=_hdr())
    assert r.status_code == 404, r.text


def test_delete_profile_entry_idempotent():
    _put_entry("interest", "tmp", "x")
    r1 = client.delete(f"/api/v1/me/profile/interest/tmp", headers=_hdr())
    assert r1.status_code == 204, r1.text
    r2 = client.delete(f"/api/v1/me/profile/interest/tmp", headers=_hdr())
    assert r2.status_code == 204, r2.text


# ------------------------------------------------------------------ 归属：不同用户不可见（current_user 已限定 user_id）


def test_entries_isolated_by_user():
    _put_entry("learning", "mine", "我的", user_id="u_a")
    _put_entry("learning", "theirs", " theirs", user_id="u_b")
    r = client.get(f"/api/v1/me/profile/learning", headers=_hdr("u_a"))
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["key"] == "mine"

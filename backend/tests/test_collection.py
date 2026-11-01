"""收藏条目路由测试（E 板块·个人中心，契约 v1.16.0）。

对照 product-redesign-target.md：
- 第 966 行 D46：收藏体系——**存快照不存引用**；内容不可编辑但支持高亮与「虚化」自测；
  反复收藏覆盖并轻提示；导出二期。
- 第 966 行 D47：chat 收藏→个人中心；内置分组是筛选维度、自定义分组是标签字段。
- 第 828 行：反复收藏覆盖。
- 第 826 行：虚化状态需持久化（#41）。

conftest 的 _reset_db 会在每个测试前清空所有表，故测试之间相互隔离。
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

U = "u_10237"
OTHER = "u_99999"


def _hdr(user_id: str = U) -> dict:
    return {"X-User-ID": user_id}


def _create_collection(name: str, user_id: str = U):
    return client.post(
        "/api/v1/me/collection", json={"name": name}, headers=_hdr(user_id)
    )


def _create_item(
    content: str = "黑洞是时空的一个区域，其引力场强到光都无法逃逸。",
    *,
    collection_id: str | None = None,
    title: str | None = None,
    user_id: str = U,
):
    payload = {
        "snapshot": {"content": content, "format": "markdown"},
    }
    if collection_id is not None:
        payload["collectionId"] = collection_id
    if title is not None:
        payload["title"] = title
    return client.post(
        "/api/v1/me/collection/items", json=payload, headers=_hdr(user_id)
    )


# ------------------------------------------------------------------ 分组


def test_list_collections_empty():
    r = client.get("/api/v1/me/collection", headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


def test_create_collection():
    r = _create_collection("计划")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "计划"
    assert body["collectionId"].startswith("col_")
    assert body["itemCount"] == 0
    assert body["createdAt"]


def test_create_collection_duplicate_returns_409():
    assert _create_collection("计划").status_code == 201
    r = _create_collection("计划")
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "STATE_CONFLICT"


def test_create_collection_builtin_name_returns_400():
    r = _create_collection("学科")
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_rename_collection():
    cid = _create_collection("计划").json()["collectionId"]
    r = client.patch(
        f"/api/v1/me/collection/{cid}",
        json={"name": "闲聊"},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "闲聊"


def test_rename_collection_not_found():
    r = client.patch(
        "/api/v1/me/collection/col_missing",
        json={"name": "x"},
        headers=_hdr(),
    )
    assert r.status_code == 404, r.text


def test_delete_collection_unassigns_items():
    cid = _create_collection("计划").json()["collectionId"]
    item_id = _create_item(collection_id=cid).json()["itemId"]

    r = client.delete(f"/api/v1/me/collection/{cid}", headers=_hdr())
    assert r.status_code == 204, r.text

    # 条目仍在，只是被移出分组（不连带删除）
    r = client.get(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["collectionId"] is None

    # 分组已不存在
    r = client.patch(
        f"/api/v1/me/collection/{cid}", json={"name": "x"}, headers=_hdr()
    )
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ 条目：新建


def test_create_item_stores_snapshot():
    r = _create_item(content="傅里叶变换把时域信号转到频域。", title="傅里叶")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["itemId"].startswith("citem_")
    assert body["title"] == "傅里叶"
    # D46 硬约束：存的是**快照本体**，不是引用
    assert body["snapshot"]["content"] == "傅里叶变换把时域信号转到频域。"
    assert body["snapshot"]["format"] == "markdown"
    assert body["highlights"] == []
    assert body["blurStates"] == []


def test_create_item_with_group_and_source_ref():
    cid = _create_collection("计划").json()["collectionId"]
    r = client.post(
        "/api/v1/me/collection/items",
        json={
            "collectionId": cid,
            "title": "黑洞",
            "snapshot": {"content": "黑洞不发光。", "format": "plain"},
            "sourceRef": {
                "type": "chat_message",
                "refId": "msg_1",
                "label": "闲聊问答",
                "subject": "WL",
            },
        },
        headers=_hdr(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["collectionId"] == cid
    assert body["sourceRef"]["type"] == "chat_message"
    assert body["sourceRef"]["refId"] == "msg_1"
    assert body["sourceRef"]["subject"] == "WL"


def test_create_item_unknown_group_returns_404():
    r = _create_item(collection_id="col_missing")
    assert r.status_code == 404, r.text


def test_repeat_collect_overwrites_not_duplicates():
    """#52：同一条内容反复收藏 → 覆盖，不新增副本。"""
    first = _create_item(content="同一段内容。")
    assert first.status_code == 201
    second = _create_item(content="同一段内容。", title="新标题")
    assert second.status_code == 201
    # 返回的是同一条（itemId 相同）
    assert second.json()["itemId"] == first.json()["itemId"]
    assert second.json()["title"] == "新标题"

    r = client.get("/api/v1/me/collection/items", headers=_hdr())
    assert len(r.json()["items"]) == 1


# ------------------------------------------------------------------ 条目：读取


def test_list_items_sorted_and_filtered():
    cid = _create_collection("计划").json()["collectionId"]
    _create_item(content="A")
    _create_item(content="B", collection_id=cid)

    all_items = client.get("/api/v1/me/collection/items", headers=_hdr()).json()["items"]
    assert len(all_items) == 2

    filtered = client.get(
        "/api/v1/me/collection/items",
        params={"collectionId": cid},
        headers=_hdr(),
    ).json()["items"]
    assert len(filtered) == 1
    assert filtered[0]["snapshot"]["content"] == "B"


def test_get_item_not_found():
    r = client.get("/api/v1/me/collection/items/citem_missing", headers=_hdr())
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ 条目：更新（高亮 / 虚化持久化）


def test_patch_item_persists_blur_states():
    """#41 / §4.8.4：虚化状态必须持久化，否则每次展开都要重设。"""
    item_id = _create_item().json()["itemId"]
    r = client.patch(
        f"/api/v1/me/collection/items/{item_id}",
        json={"blurStates": [{"start": 0, "end": 4}, {"start": 10, "end": 14}]},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["blurStates"]) == 2

    # 重新读取仍然在（持久化到库）
    again = client.get(
        f"/api/v1/me/collection/items/{item_id}", headers=_hdr()
    ).json()
    assert again["blurStates"] == [
        {"start": 0, "end": 4},
        {"start": 10, "end": 14},
    ]


def test_patch_item_persists_highlights():
    item_id = _create_item().json()["itemId"]
    r = client.patch(
        f"/api/v1/me/collection/items/{item_id}",
        json={"highlights": [{"start": 2, "end": 6}]},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["highlights"] == [{"start": 2, "end": 6}]
    again = client.get(
        f"/api/v1/me/collection/items/{item_id}", headers=_hdr()
    ).json()
    assert again["highlights"] == [{"start": 2, "end": 6}]


def test_patch_item_content_is_immutable():
    """D46：内容不可编辑——UPDATE schema 里没有 snapshot 字段，传了也不生效。"""
    original = "原始内容，不应被改动。"
    item_id = _create_item(content=original).json()["itemId"]
    r = client.patch(
        f"/api/v1/me/collection/items/{item_id}",
        json={"snapshot": {"content": "被篡改", "format": "plain"}},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["snapshot"]["content"] == original


def test_patch_item_can_move_out_of_group():
    cid = _create_collection("计划").json()["collectionId"]
    item_id = _create_item(collection_id=cid).json()["itemId"]
    r = client.patch(
        f"/api/v1/me/collection/items/{item_id}",
        json={"collectionId": None},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["collectionId"] is None


def test_patch_item_not_found():
    r = client.patch(
        "/api/v1/me/collection/items/citem_missing",
        json={"title": "x"},
        headers=_hdr(),
    )
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ 条目：删除


def test_delete_item_is_idempotent():
    item_id = _create_item().json()["itemId"]
    first = client.delete(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert first.status_code == 204, first.text
    second = client.delete(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert second.status_code == 204, second.text

    r = client.get(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ 归属隔离


def test_collections_isolated_by_user():
    _create_collection("我的", user_id="u_a")
    _create_collection("别人的", user_id="u_b")
    r = client.get("/api/v1/me/collection", headers=_hdr("u_a"))
    assert r.status_code == 200, r.text
    names = [c["name"] for c in r.json()["items"]]
    assert names == ["我的"]


def test_items_isolated_by_user():
    _create_item(content="我的收藏", user_id="u_a")
    _create_item(content="别人的收藏", user_id="u_b")
    r = client.get("/api/v1/me/collection/items", headers=_hdr("u_a"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["snapshot"]["content"] == "我的收藏"


def test_cannot_read_other_users_item():
    item_id = _create_item(content="别人的收藏", user_id=OTHER).json()["itemId"]
    r = client.get(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert r.status_code == 404, r.text


def test_cannot_delete_other_users_item():
    item_id = _create_item(content="别人的收藏", user_id=OTHER).json()["itemId"]
    r = client.delete(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    # 幂等删除对「别人的条目」等同「不存在」→ 204，但不得真删
    assert r.status_code == 204, r.text
    still = client.get(
        f"/api/v1/me/collection/items/{item_id}", headers=_hdr(OTHER)
    )
    assert still.status_code == 200, still.text

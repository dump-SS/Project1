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


def test_create_item_reports_created_true_for_new():
    """v1.17.1：建档与覆盖同为 201，靠 created 区分（#52 轻提示文案的依据）。"""
    r = _create_item(content="全新的一段内容。")
    assert r.status_code == 201, r.text
    assert r.json()["created"] is True


def test_repeat_collect_reports_created_false_without_any_change():
    """覆盖且 body 无可变字段时 created 仍为 False——此时不发 UPDATE，时间戳方案会误判成新建。"""
    first = _create_item(content="完全相同的内容。")
    assert first.status_code == 201, first.text
    again = _create_item(content="完全相同的内容。")
    assert again.status_code == 201, again.text
    assert again.json()["created"] is False
    assert again.json()["itemId"] == first.json()["itemId"]
    # 时间戳在这一格区分不出来，正是要用显式标记的原因
    assert again.json()["updatedAt"] == first.json()["updatedAt"]


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


# ---------------------------------------------------- sourceMap 真存（I5，方案 C 闭环）

_SOURCE_MAP = {
    "v": 1,
    "total": 99,
    "chunks": [
        {"rs": 0, "rl": 7, "ss": 2, "sl": 7},
        {"rs": 24, "rl": 5, "ss": 33, "sl": 5, "jumps": [[4, 1]]},
    ],
}


def _post_item_with_map(user_id: str = U):
    return client.post(
        "/api/v1/me/collection/items",
        json={
            "title": "映射验证",
            "snapshot": {
                "content": "**复合函数单调性**的判断核心是「同增异减」原则：",
                "format": "markdown",
                "sourceMap": _SOURCE_MAP,
            },
            "sourceRef": {"type": "manual", "label": "映射验证"},
        },
        headers=_hdr(user_id),
    )


def test_source_map_survives_post_and_readback():
    """I5 关键验收：POST 带 sourceMap → 响应 / 列表 / 单条三处都回读得到，chunks 一致。

    断的是后端 pydantic 未声明该字段时 extra=ignore 静默丢弃：契约与前端都按「已存」写好，
    只差后端收下（Skyer 2026-11-06 拍板真存）。
    """
    created = _post_item_with_map()
    assert created.status_code == 201, created.text
    body = created.json()
    item_id = body["itemId"]

    sm = body["snapshot"]["sourceMap"]
    assert sm["v"] == 1 and sm["total"] == 99
    assert len(sm["chunks"]) == 2
    assert sm["chunks"][1] == {"rs": 24, "rl": 5, "ss": 33, "sl": 5, "jumps": [[4, 1]]}

    listed = client.get("/api/v1/me/collection/items", headers=_hdr()).json()["items"]
    got = next(i for i in listed if i["itemId"] == item_id)
    assert got["snapshot"]["sourceMap"] == sm

    single = client.get(f"/api/v1/me/collection/items/{item_id}", headers=_hdr())
    assert single.status_code == 200, single.text
    assert single.json()["snapshot"]["sourceMap"] == sm


def test_source_map_is_persisted_not_just_echoed():
    """防「只在响应里回显、没落库」：直接查 snapshot_json 列里的原文。"""
    item_id = _post_item_with_map().json()["itemId"]

    from database import SessionLocal
    from models.collection import CollectionItem as CollectionItemORM

    db = SessionLocal()
    try:
        row = db.get(CollectionItemORM, item_id)
        assert row is not None, "条目没落库"
        assert "sourceMap" in row.snapshot_json, row.snapshot_json
        compact = row.snapshot_json.replace(" ", "")
        assert '"total":99' in compact, row.snapshot_json
        assert '"jumps":[[4,1]]' in compact, row.snapshot_json
    finally:
        db.close()


def test_snapshot_without_source_map_still_round_trips():
    """老快照（无 sourceMap）不受影响：不报错、字段缺省，前端展开时现算兜底不回归。"""
    r = _create_item(content="没有映射的老快照内容。")
    assert r.status_code == 201, r.text
    snap = r.json()["snapshot"]
    assert snap.get("sourceMap") is None
    assert snap["content"] == "没有映射的老快照内容。"


def test_upload_summary_path_persists_source_map():
    """#47 摘要进收藏链路：载荷与前端 ChatCards 的 FileSummaryCard 一致，
    直查 snapshot_json 列原文含 sourceMap（证明并轨后这条入口也真落库，不是回显）。

    前端并轨前走 services/collections.ts（无 sourceMap），方案 C 只覆盖 Chat 收藏一条；
    并轨到 collectItem 后两条入口都带映射。
    """
    summary = "**要点**：牛顿第二定律 F = ma\n\n- 力是改变运动状态的原因\n"
    map_payload = {
        "v": 1,
        "total": 24,
        "chunks": [
            {"rs": 0, "rl": 2, "ss": 2, "sl": 2},
            {"rs": 2, "rl": 12, "ss": 4, "sl": 12, "jumps": [[4, 1]]},
        ],
    }
    created = client.post(
        "/api/v1/me/collection/items",
        json={
            "title": "上传照片摘要",
            "snapshot": {
                "content": summary,
                "format": "markdown",
                "sourceMap": map_payload,
            },
            "sourceRef": {
                "type": "upload_summary",
                "refId": "media_dev8_key",
                "label": "上传照片摘要",
            },
        },
        headers=_hdr(),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created"] is True
    # 注意：pydantic 会把未提供的可选 jumps 序列化为 null，所以按字段断言，不做整字典相等
    sm = body["snapshot"]["sourceMap"]
    assert sm["v"] == 1 and sm["total"] == 24
    assert len(sm["chunks"]) == 2
    assert sm["chunks"][0] == {"rs": 0, "rl": 2, "ss": 2, "sl": 2, "jumps": None}
    assert sm["chunks"][1] == {"rs": 2, "rl": 12, "ss": 4, "sl": 12, "jumps": [[4, 1]]}

    from database import SessionLocal
    from models.collection import CollectionItem as CollectionItemORM

    db = SessionLocal()
    try:
        row = db.get(CollectionItemORM, body["itemId"])
        assert row is not None
        assert "sourceMap" in row.snapshot_json, row.snapshot_json
        compact = row.snapshot_json.replace(" ", "")
        assert '"total":24' in compact, row.snapshot_json
        assert '"jumps":[[4,1]]' in compact, row.snapshot_json
        # 来源类型存在 source_ref_json 列（sourceRef 不在 snapshot_json 里），#47 的溯源口径不变
        assert '"type":"upload_summary"' in row.source_ref_json.replace(" ", ""), row.source_ref_json
    finally:
        db.close()

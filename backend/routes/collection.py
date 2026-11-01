"""收藏条目路由（E 板块·个人中心，契约 v1.16.0）。

对照 product-redesign-target.md：
- 第 966 行 D46：收藏体系——任意模型输出可收藏，**存快照不存引用**；
  不进知识点库、不参与 mastery/难度/图谱；内容不可编辑但支持高亮与「虚化」自测；
  反复收藏覆盖并轻提示；导出二期。
- 第 966 行 D47：知识资产归位——chat 收藏→个人中心（不可评测）；
  内置分组是筛选维度、自定义分组是标签字段，两者正交；
  展现为卡片+来源引用，不做文本直列。
- 第 828 行：反复收藏覆盖，给轻提示「已更新这个收藏」。
- 第 826 行：虚化状态需持久化（#41）。

归属：所有端点走 current_user（sid cookie），天然只查本人 user_id，不越路。

⚠️ `collection_items` 的 snapshot / source_ref / highlight / blur_state 四列都是 **Text**
（存 JSON 字符串，见 models/collection.py 的「统一存 JSON 文本列」注释），所以本模块
负责 dict/list ↔ JSON 字符串的双向转换；不要直接把 dict 塞进模型列。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.collection import Collection as CollectionORM
from models.collection import CollectionItem as CollectionItemORM
from models.user import User as UserORM
from schemas.collection import (
    Collection,
    CollectionCreate,
    CollectionItem,
    CollectionItemCreate,
    CollectionItemList,
    CollectionItemUpdate,
    CollectionList,
    CollectionUpdate,
)
from .deps import current_user

router = APIRouter(prefix="", tags=["收藏"])

#: 内置分组（筛选维度，不入表；D47 明写「内置分组是筛选维度、自定义分组是标签字段」）
_BUILTIN_GROUPS = {"学科", "时间", "掌握度"}


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _loads(raw: str | None) -> Any:
    """把 Text 列里的 JSON 字符串读回对象；坏数据不拖垮整个响应。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _dumps(obj: Any) -> str | None:
    """把对象序列化成 JSON 字符串存 Text 列；None 保持 None。"""
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def _serialize_collection(row: CollectionORM, item_count: int) -> Collection:
    return Collection(
        collectionId=row.id,
        name=row.name,
        itemCount=item_count,
        createdAt=row.created_at,
        updatedAt=row.created_at,  # 模型暂无 updated_at 列，暂以 created_at 占位
    )


def _serialize_item(row: CollectionItemORM) -> CollectionItem:
    snapshot = _loads(row.snapshot_json) or {"content": "", "format": "markdown"}
    return CollectionItem(
        itemId=row.id,
        collectionId=row.collection_id,
        title=row.title,
        snapshot=snapshot,
        sourceRef=_loads(row.source_ref_json),
        highlights=_loads(row.highlight_json) or [],
        blurStates=_loads(row.blur_state_json) or [],
        createdAt=row.created_at,
    )


def _count_items(db: Session, user_id: str, collection_id: str) -> int:
    return (
        db.query(CollectionItemORM)
        .filter(
            CollectionItemORM.user_id == user_id,
            CollectionItemORM.collection_id == collection_id,
        )
        .count()
    )


def _get_owned_collection(
    db: Session, user_id: str, collection_id: str
) -> CollectionORM:
    row = (
        db.query(CollectionORM)
        .filter(
            CollectionORM.id == collection_id,
            CollectionORM.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "分组不存在"},
        )
    return row


def _get_owned_item(db: Session, user_id: str, item_id: str) -> CollectionItemORM:
    row = (
        db.query(CollectionItemORM)
        .filter(
            CollectionItemORM.id == item_id,
            CollectionItemORM.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "条目不存在"},
        )
    return row


# =============================================================================
# 分组
# =============================================================================


@router.get(
    "/me/collection",
    response_model=CollectionList,
    summary="获取用户的全部收藏分组",
)
def list_collections(
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> CollectionList:
    rows = (
        db.query(CollectionORM)
        .filter(CollectionORM.user_id == user.user_id)
        .order_by(CollectionORM.created_at.desc())
        .all()
    )
    return CollectionList(
        items=[
            _serialize_collection(r, _count_items(db, user.user_id, r.id))
            for r in rows
        ]
    )


@router.post(
    "/me/collection",
    response_model=Collection,
    status_code=status.HTTP_201_CREATED,
    summary="创建自定义收藏分组",
)
def create_collection(
    body: CollectionCreate,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> Collection:
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "分组名不能为空",
                "field": "name",
            },
        )
    if name in _BUILTIN_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"「{name}」是内置分组，不可新建",
                "field": "name",
            },
        )
    existing = (
        db.query(CollectionORM)
        .filter(
            CollectionORM.user_id == user.user_id,
            CollectionORM.name == name,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": f"分组「{name}」已存在",
            },
        )
    row = CollectionORM(id=_gen_id("col"), user_id=user.user_id, name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_collection(row, 0)


@router.patch(
    "/me/collection/{collectionId}",
    response_model=Collection,
    summary="重命名收藏分组",
)
def update_collection(
    collectionId: str,
    body: CollectionUpdate,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> Collection:
    row = _get_owned_collection(db, user.user_id, collectionId)
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "分组名不能为空",
                "field": "name",
            },
        )
    if name in _BUILTIN_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"「{name}」是内置分组，不可重命名为该名称",
                "field": "name",
            },
        )
    existing = (
        db.query(CollectionORM)
        .filter(
            CollectionORM.user_id == user.user_id,
            CollectionORM.name == name,
            CollectionORM.id != collectionId,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": f"分组「{name}」已存在",
            },
        )
    row.name = name
    db.commit()
    db.refresh(row)
    return _serialize_collection(
        row, _count_items(db, user.user_id, row.id)
    )


@router.delete(
    "/me/collection/{collectionId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="删除自定义收藏分组（内置分组不可删）",
)
def delete_collection(
    collectionId: str,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> None:
    row = _get_owned_collection(db, user.user_id, collectionId)
    if row.name in _BUILTIN_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "内置分组不可删除"},
        )
    # 组内条目只解除分组归属，不连带删除（条目本身由 DELETE item 单独管理）
    db.query(CollectionItemORM).filter(
        CollectionItemORM.user_id == user.user_id,
        CollectionItemORM.collection_id == collectionId,
    ).update({CollectionItemORM.collection_id: None}, synchronize_session=False)
    db.delete(row)
    db.commit()
    return None


# =============================================================================
# 条目
# =============================================================================


@router.get(
    "/me/collection/items",
    response_model=CollectionItemList,
    summary="获取用户全部收藏条目（按时间倒序）",
)
def list_collection_items(
    collectionId: str | None = None,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> CollectionItemList:
    q = db.query(CollectionItemORM).filter(
        CollectionItemORM.user_id == user.user_id
    )
    if collectionId is not None:
        q = q.filter(CollectionItemORM.collection_id == collectionId)
    rows = q.order_by(CollectionItemORM.created_at.desc()).all()
    return CollectionItemList(items=[_serialize_item(r) for r in rows])


@router.get(
    "/me/collection/items/{itemId}",
    response_model=CollectionItem,
    summary="获取单条收藏条目",
)
def get_collection_item(
    itemId: str,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> CollectionItem:
    return _serialize_item(_get_owned_item(db, user.user_id, itemId))


@router.post(
    "/me/collection/items",
    response_model=CollectionItem,
    status_code=status.HTTP_201_CREATED,
    summary="新增收藏条目（反复收藏同一内容 → 覆盖）",
)
def create_collection_item(
    body: CollectionItemCreate,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> CollectionItem:
    if body.collectionId is not None:
        _get_owned_collection(db, user.user_id, body.collectionId)

    # 去重键 = 快照本体（content + format + imageRef）。同一内容反复收藏 → 覆盖（#52），
    # 不新增副本。用规范化 JSON 比较，字段顺序由 pydantic 固定，顺序稳定。
    snapshot_str = _dumps(body.snapshot.model_dump(mode="json"))
    source_ref_str = (
        _dumps(body.sourceRef.model_dump(mode="json"))
        if body.sourceRef is not None
        else None
    )

    existing = (
        db.query(CollectionItemORM)
        .filter(
            CollectionItemORM.user_id == user.user_id,
            CollectionItemORM.snapshot_json == snapshot_str,
        )
        .first()
    )
    if existing is not None:
        # 覆盖：只更新可变字段；快照本身不再改（内容不可编辑，D46）
        if body.title is not None:
            existing.title = body.title
        if body.collectionId is not None:
            existing.collection_id = body.collectionId
        if source_ref_str is not None:
            existing.source_ref_json = source_ref_str
        db.commit()
        db.refresh(existing)
        return _serialize_item(existing)

    row = CollectionItemORM(
        id=_gen_id("citem"),
        user_id=user.user_id,
        collection_id=body.collectionId,
        title=body.title,
        snapshot_json=snapshot_str,
        source_ref_json=source_ref_str,
        highlight_json=None,
        blur_state_json=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_item(row)


@router.patch(
    "/me/collection/items/{itemId}",
    response_model=CollectionItem,
    summary="局部更新收藏条目（只改分组/标题/高亮/虚化，内容不可编辑）",
)
def update_collection_item(
    itemId: str,
    body: CollectionItemUpdate,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> CollectionItem:
    row = _get_owned_item(db, user.user_id, itemId)

    # 显式区分「字段没传」与「显式传 null」：
    #   collectionId 传 null = 移出分组；不传 = 保持不变。
    fields_set = body.model_fields_set
    if "collectionId" in fields_set:
        if body.collectionId is not None:
            _get_owned_collection(db, user.user_id, body.collectionId)
        row.collection_id = body.collectionId
    if body.title is not None:
        row.title = body.title
    if body.highlights is not None:
        # 全量覆盖（不是增量）：前端一次提交当前全部区间
        row.highlight_json = _dumps(
            [h.model_dump(mode="json") for h in body.highlights]
        )
    if body.blurStates is not None:
        # 虚化状态持久化（#41）：否则每次展开都要重设
        row.blur_state_json = _dumps(
            [b.model_dump(mode="json") for b in body.blurStates]
        )
    db.commit()
    db.refresh(row)
    return _serialize_item(row)


@router.delete(
    "/me/collection/items/{itemId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="删除收藏条目（幂等）",
)
def delete_collection_item(
    itemId: str,
    db: Session = Depends(get_db),
    user: UserORM = Depends(current_user),
) -> None:
    row = (
        db.query(CollectionItemORM)
        .filter(
            CollectionItemORM.id == itemId,
            CollectionItemORM.user_id == user.user_id,
        )
        .first()
    )
    if row is None:
        # 幂等：不存在也返回 204（与 /f/media 的删除口径一致）
        return None
    db.delete(row)
    db.commit()
    return None

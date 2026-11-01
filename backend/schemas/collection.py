"""收藏条目 schema（openapi.yaml v1.16.0）。

对照 product-redesign-target.md：
- 第 966 行 D46：收藏体系——任意模型输出可收藏，**存快照不存引用**；
  不进知识点库、不参与 mastery/难度/图谱；内容不可编辑但支持高亮与「虚化」自测；
  反复收藏覆盖并轻提示；导出二期。
- 第 966 行 D47：知识资产归位——chat 收藏→个人中心（不可评测）；
  内置分组是筛选维度、自定义分组是标签字段，两者正交；
  展现为卡片+来源引用，不做文本直列。
- 第 828 行：反复收藏覆盖，给轻提示「已更新这个收藏」。
- 第 826 行：虚化状态需持久化（#41）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import Subject


class Collection(BaseModel):
    """收藏的自定义分组。"""

    model_config = ConfigDict(populate_by_name=True)

    collectionId: str = Field(..., description="分组 ID")
    name: str = Field(..., max_length=64, description="用户自建分组名（如「计划」「闲聊」）")
    itemCount: int = Field(..., description="组内条目数（列表接口按需下发）")
    createdAt: datetime = Field(..., description="创建时间")
    updatedAt: datetime | None = Field(None, description="最近更新时间（分组可重命名，见 CollectionUpdate）")

class CollectionCreate(BaseModel):
    """新增收藏分组请求体。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., max_length=64, description="用户自建分组名（如「计划」「闲聊」）")


class CollectionList(BaseModel):
    """分组列表。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[Collection] = Field(..., description="分组条目")


class CollectionUpdate(BaseModel):
    """重命名收藏分组请求体。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., max_length=64, description="分组新名")


class CollectionSnapshot(BaseModel):
    """收藏内容的**快照**（D46 硬约束）。"""

    model_config = ConfigDict(populate_by_name=True)

    content: str = Field(..., description="收藏时的正文快照（原样保存，不随原文过期而失效）")
    format: str = Field(
        "markdown",
        description="content 的文本格式。模型输出多为 Markdown，收藏时**原样保存格式**。",
    )
    imageRef: str | None = Field(
        None,
        description="裁剪后小图的存储引用（图片圈选场景）",
    )


class CollectionSourceRef(BaseModel):
    """来源引用（仅用于溯源标注，不承担内容可读性）。"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(
        ...,
        description="来源类型：chat_message / explanation / search_answer / knowledge_point / upload_summary / manual",
    )
    refId: str | None = Field(None, description="来源条目 ID")
    label: str | None = Field(None, description="来源标签")
    subject: Subject | None = Field(None, description="学科")


class CollectionHighlight(BaseModel):
    """划选高亮（内容不可编辑，高亮只改显示）。"""

    model_config = ConfigDict(populate_by_name=True)

    start: int = Field(..., description="起始偏移（按 Unicode 码点计，左闭右开）")
    end: int = Field(..., description="结束偏移（按 Unicode 码点计，左闭右开）")


class CollectionBlurState(BaseModel):
    """「虚化」标记（#41 / §4.8.4）：把选中文本做模糊显示，用于隐藏信息或自测（填空题）。

    虚化不算编辑——只改显示不改内容，状态必须持久化。
    """

    model_config = ConfigDict(populate_by_name=True)

    start: int = Field(..., description="起始偏移（按 Unicode 码点计，口径同 CollectionHighlight）")
    end: int = Field(..., description="结束偏移（按 Unicode 码点计，左闭右开）")


class CollectionItem(BaseModel):
    """收藏条目。内容不可编辑（保证留存真实性），只支持高亮与虚化标记。"""

    model_config = ConfigDict(populate_by_name=True)

    itemId: str = Field(..., description="条目 ID")
    collectionId: str | None = Field(
        None, description="自定义分组 ID；未分组为 null（内置维度不入表）"
    )
    title: str | None = Field(None, description="条目标题")
    snapshot: CollectionSnapshot = Field(..., description="收藏时的正文快照")
    sourceRef: CollectionSourceRef | None = Field(
        None, description="来源引用（仅用于溯源标注）"
    )
    highlights: list[CollectionHighlight] = Field(
        default_factory=list, description="划选高亮区间"
    )
    blurStates: list[CollectionBlurState] = Field(
        default_factory=list, description="虚化区间；全屏展开时方向键切换焦点、空格临时解除"
    )
    createdAt: datetime = Field(..., description="创建时间")


class CollectionItemCreate(BaseModel):
    """新增收藏。同一条内容反复收藏 → 覆盖并给轻提示（#52），不新增副本。"""

    model_config = ConfigDict(populate_by_name=True)

    collectionId: str | None = Field(None, description="自定义分组 ID；未分组为 null")
    title: str | None = Field(None, description="条目标题")
    snapshot: CollectionSnapshot = Field(..., description="收藏时的正文快照")
    sourceRef: CollectionSourceRef | None = Field(
        None, description="来源引用（仅用于溯源标注）"
    )


class CollectionItemList(BaseModel):
    """条目列表。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[CollectionItem] = Field(..., description="条目列表")


class CollectionItemUpdate(BaseModel):
    """收藏条目的标记更新。**内容不可编辑**（保证留存真实性，D46），
    只能改分组、标题、高亮与虚化标记。虚化必须可持久化（#41）。
    """

    model_config = ConfigDict(populate_by_name=True)

    collectionId: str | None = Field(
        None, description="移动到自定义分组；传 null 表示移出分组"
    )
    title: str | None = Field(None, description="条目标题")
    highlights: list[CollectionHighlight] | None = Field(
        None,
        description="高亮区间**全量覆盖**（不是增量），前端一次提交当前全部区间",
    )
    blurStates: list[CollectionBlurState] | None = Field(
        None,
        description="虚化区间**全量覆盖**；「全部虚化」一键即提交完整列表",
    )


class CollectionUpdate(BaseModel):
    """重命名收藏分组请求体（自定义分组是用户标签字段，与内置筛选维度正交）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., max_length=64, description="分组新名")


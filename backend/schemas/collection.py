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
from .common import APIModel

from .enums import Subject


class Collection(APIModel):
    """收藏的自定义分组。"""

    model_config = ConfigDict(populate_by_name=True)

    collectionId: str = Field(..., description="分组 ID")
    name: str = Field(..., max_length=64, description="用户自建分组名（如「计划」「闲聊」）")
    itemCount: int = Field(..., description="组内条目数（列表接口按需下发）")
    createdAt: datetime = Field(..., description="创建时间")
    updatedAt: datetime | None = Field(None, description="最近更新时间（分组可重命名，见 CollectionUpdate）")

class CollectionCreate(APIModel):
    """新增收藏分组请求体。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., max_length=64, description="用户自建分组名（如「计划」「闲聊」）")


class CollectionList(APIModel):
    """分组列表。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[Collection] = Field(..., description="分组条目")


class CollectionUpdate(APIModel):
    """重命名收藏分组请求体（自定义分组是用户标签字段，与内置筛选维度正交）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., max_length=64, description="分组新名")


class SnapshotSourceMapChunk(APIModel):
    """一段「渲染文本 ↔ 原文」对齐区间（码点），见契约 SnapshotSourceMapChunk。"""

    model_config = ConfigDict(populate_by_name=True)

    rs: int = Field(..., description="渲染文本码点起点")
    rl: int = Field(..., description="渲染文本码点长度")
    ss: int = Field(..., description="原文码点起点")
    sl: int = Field(..., description="原文码点长度")
    jumps: list[tuple[int, int]] | None = Field(
        None,
        description="转义/字符引用处的 [渲染 chunk 内偏移, 累计多消耗的源码点数]，升序",
    )


class SnapshotSourceMap(APIModel):
    """方案 C（Skyer 2026-11-03 拍板）：保存时算好的渲染↔原文映射，划选时查表不实时算。"""

    model_config = ConfigDict(populate_by_name=True)

    v: int = Field(..., description="映射格式版本，当前 1")
    total: int | None = Field(
        None, description="渲染文本总码点长（含块间合成换行）；老映射可缺省"
    )
    chunks: list[SnapshotSourceMapChunk] = Field(default_factory=list)


class CollectionSnapshot(APIModel):
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
    sourceMap: SnapshotSourceMap | None = Field(
        None,
        description=(
            "markdown 快照的渲染↔原文映射（方案 C：保存时一次性算好存起来，划选时查表）。"
            "此前契约已声明、后端未声明该字段，pydantic 默认 extra=ignore 把它静默丢弃，"
            "导致前端只能每次展开现算；本字段补上即兑现契约。后端只透传，不解释。"
        ),
    )


class CollectionSourceRef(APIModel):
    """来源引用（仅用于溯源标注，不承担内容可读性）。"""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(
        ...,
        description="来源类型：chat_message / explanation / search_answer / knowledge_point / upload_summary / manual",
    )
    refId: str | None = Field(None, description="来源条目 ID")
    label: str | None = Field(None, description="来源标签")
    subject: Subject | None = Field(None, description="学科")


class CollectionHighlight(APIModel):
    """划选高亮（内容不可编辑，高亮只改显示）。"""

    model_config = ConfigDict(populate_by_name=True)

    start: int = Field(..., description="起始偏移（按 Unicode 码点计，左闭右开）")
    end: int = Field(..., description="结束偏移（按 Unicode 码点计，左闭右开）")


class CollectionBlurState(APIModel):
    """「虚化」标记（#41 / §4.8.4）：把选中文本做模糊显示，用于隐藏信息或自测（填空题）。

    虚化不算编辑——只改显示不改内容，状态必须持久化。
    """

    model_config = ConfigDict(populate_by_name=True)

    start: int = Field(..., description="起始偏移（按 Unicode 码点计，口径同 CollectionHighlight）")
    end: int = Field(..., description="结束偏移（按 Unicode 码点计，左闭右开）")


class CollectionItem(APIModel):
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
    updatedAt: datetime | None = Field(
        None,
        description=(
            "最近更新时间（契约 v1.17.1 补下发）。collection_items.updated_at 列自 M0 起"
            "就存在且带 onupdate，此前只是没进契约、没下发。仅供展示，不要用它判断建档/覆盖。"
        ),
    )


class CollectionItemCreateResult(CollectionItem):
    """POST /me/collection/items 的响应体：条目全字段 + created 标记（#52 轻提示的依据）。"""

    created: bool = Field(
        ...,
        description=(
            "true = 本次新建条目；false = 命中同一快照、覆盖既有条目（返回同一个 itemId）。"
            "建档与覆盖同为 201，时间戳比对不可靠（SQLite 秒级精度，且覆盖分支在 body"
            "未带可变字段时不产生 UPDATE），所以用显式标记。"
        ),
    )


class CollectionItemCreate(APIModel):
    """新增收藏。同一条内容反复收藏 → 覆盖并给轻提示（#52），不新增副本。"""

    model_config = ConfigDict(populate_by_name=True)

    collectionId: str | None = Field(None, description="自定义分组 ID；未分组为 null")
    title: str | None = Field(None, description="条目标题")
    snapshot: CollectionSnapshot = Field(..., description="收藏时的正文快照")
    sourceRef: CollectionSourceRef | None = Field(
        None, description="来源引用（仅用于溯源标注）"
    )


class CollectionItemList(APIModel):
    """条目列表。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[CollectionItem] = Field(..., description="条目列表")


class CollectionItemUpdate(APIModel):
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


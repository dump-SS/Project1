"""搜题归档 + 讲解归档 schema（D 板块 / §3.8.4 / D24 / D52）。

契约对应 `docs/openapi.yaml` v1.7.1：
- `SearchMode` / `SearchArchive`
- `ExplanationMode` / `Explanation`
- `KnowledgeRef`（已同意登记，文本见 ``docs/refactor-d-knowledge-ref-protocol.md``）

两处**待 X0 登记的契约增量**（见 handoff §1.2，实现先按此写）：
1. ``SearchArchive.pointIds`` 的 items 由 ``string`` 改为 ``KnowledgeRef``——
   三态结尾统一输出的知识点卡片必须带 ``mastery``，纯 id 数组撑不起这张卡。
2. ``SearchArchive`` 增 ``solutions``（≤3 条）与 ``solutionCount``——
   D52 要求「多解分页 ≤3，默认只给主解」，``solution`` 仍为主解正文。
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# D24 三态：直给 / 解析式 / 引导式。**记忆上次选择**，故必须落库。
SEARCH_MODES = ("direct", "analytic", "guided")
SearchMode = Literal["direct", "analytic", "guided"]

# D52 讲解两态：回顾取原文 / 重新讲现生成。两者并存，不互相顶掉。
EXPLANATION_MODES = ("original", "regenerated")
ExplanationMode = Literal["original", "regenerated"]

# D52 多解上限：默认只给主解，最多 3 条
MAX_SOLUTIONS = 3


class KnowledgeRef(BaseModel):
    """知识引用协议（`refactor-d-knowledge-ref-protocol.md`，文本已冻结）。

    四字段，消费方**不得自行扩展**——扩展即等于绕过 mastery 口径。
    ``mastery`` 为 null 表示样本不足（≠ 0）；库外知识 ``pointId`` 为 null。
    """

    model_config = ConfigDict(populate_by_name=True)

    point_id: Optional[str] = Field(None, alias="pointId")
    subject_code: Optional[str] = Field(None, alias="subjectCode")
    name: str
    mastery: Optional[float] = Field(
        None, ge=0.0, le=1.0, alias="mastery",
        description="null = 样本不足，不是 0；库外知识恒为 null",
    )


class SearchArchiveCreate(BaseModel):
    """发起一次搜题（用户即时动作）。"""

    model_config = ConfigDict(populate_by_name=True)

    subject: Optional[str] = Field(None, alias="subject")
    raw_text: str = Field(..., alias="rawText", max_length=4000)
    # 不传 = 沿用上次选择（D24「三态可切换且被记忆」）
    mode: Optional[SearchMode] = Field(None, alias="mode")


class SearchArchive(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    archive_id: str = Field(..., alias="archiveId")
    subject: Optional[str] = Field(None, alias="subject")
    raw_text: str = Field(..., alias="rawText")
    solution: Optional[str] = Field(None, alias="solution", description="主解正文")
    mode: Optional[SearchMode] = Field(None, alias="mode")
    point_ids: List[KnowledgeRef] = Field(
        [], alias="pointIds", description="结尾统一输出的知识点卡片"
    )
    # D52 多解分页：≤3，默认只回主解
    solutions: List[str] = Field([], alias="solutions")
    solution_count: int = Field(0, alias="solutionCount")
    created_at: str = Field(..., alias="createdAt")


class SearchArchiveList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[SearchArchive]
    pagination: dict


class ExplanationCreate(BaseModel):
    """生成 / 取回一条讲解。

    ``mode=original``：回顾取原文（不调模型，取该用户该知识点最近一条归档）。
    ``mode=regenerated``：重新讲、现生成一条并入库。两者并存。
    """

    model_config = ConfigDict(populate_by_name=True)

    point_id: Optional[str] = Field(None, alias="pointId")
    subject: Optional[str] = Field(None, alias="subject")
    mode: ExplanationMode = Field("regenerated", alias="mode")


class Explanation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    explanation_id: str = Field(..., alias="explanationId")
    point_id: Optional[str] = Field(None, alias="pointId")
    subject: Optional[str] = Field(None, alias="subject")
    mode: ExplanationMode = Field(..., alias="mode")
    content: str = Field(..., alias="content")
    is_curated: bool = Field(False, alias="isCurated")
    created_at: str = Field(..., alias="createdAt")


class ExplanationList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[Explanation]
    pagination: dict

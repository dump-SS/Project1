"""搜题（D24）+ 讲解归档（D52）—— D 板块知识页两条链路。

对应契约 v1.7.1 的 `SearchArchive` / `Explanation` / `SearchMode` / `ExplanationMode`。
路径用**复数资源名**（`/search-archives`、`/explanations`），与既有单数 `/error-book`
不同是历史遗留，评审已确认不为了迁就旧命名去改新资源。

## 出域口径（2026-09-30 拍板，见 egress_guard.USER_ERROR_CONTENT）

搜题在工程上必须把题面交给模型，这与「knowledge_raw 永不出域」正面冲突。
拍板结论：**不看「存没存过」，看「这次是不是用户主动发起 + 内容是不是用户自己的」**。
用户当场输入 / 拍照的题面 → 新增 `user_error_content` 类，允许出域；
知识点库原始素材 → 仍是 `knowledge_raw`，永不出域。

放宽的四道加固，本文件逐条落地：

1. **每次点击即一次授权**——只有 `POST /search-archives` 这个用户即时请求会触发出域，
   模块内**没有任何 BackgroundTasks / 定时任务 / 批量导出**（`test_search_egress.py`
   直接扫源码断言这一点）。生成在请求内同步完成，请求结束即授权结束。
2. **优先境内服务商**——沿用 `llm_provider` 的 `llm_base_url`，配境内供应商即可；
   本文件不引入任何第二家供应商或直连地址。
3. **用户可关闭**——`settings.knowledge_ai_egress_enabled`（默认关闭）。关闭时
   **退回本地检索 + 通用讲解**：只发 `knowledge_aggregated` 白名单字段，
   题面一个字都不出去。
4. **出域留痕**——放行时调 `egress_log.log_egress_allowed`（用户 / 内容类型 / 时间）。

另外「能走聚合就走聚合」：只有 `direct` 态（要真解出这道题）才需要题面；
`analytic` / `guided` 先走知识点聚合，拿不到足够信息再按开关决定是否上题面。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from egress_guard import (
    KNOWLEDGE_AGGREGATED,
    USER_ERROR_CONTENT,
    Guard,
)
from egress_log import log_egress_allowed
from mastery_engine import compute_mastery, gather_inputs
from models.explanation import Explanation as ExplanationORM
from models.knowledge import KnowledgePoint as KnowledgePointORM
from models.search import SearchArchive as SearchArchiveORM
from schemas.search import (
    MAX_SOLUTIONS,
    SEARCH_MODES,
    Explanation,
    ExplanationCreate,
    ExplanationList,
    KnowledgeRef,
    SearchArchive,
    SearchArchiveCreate,
    SearchArchiveList,
)
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["搜题与讲解"])

# 语言类学科：结尾附「查词卡」模板 + 出处回溯（D52）
_LANG_SUBJECTS = {"YW", "YY"}
# 契约 Subject 枚举里英语是 EN，种子库里是 YY，两个都认
_LANG_SUBJECTS |= {"EN"}

# D52 多解上限
_MAX_SOLUTIONS = MAX_SOLUTIONS


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------

SOLUTION_SYSTEM = """你是一个中学学科辅导助手，像特级教师当面讲题。

硬约束：
- **只允许使用中学（初中/高中）课程标准内的方法**。禁止超纲解法
  （例：用洛必达法则 / 泰勒展开解高中导数题，用向量外积 / 复数解初中几何，
  用大学线性代数解高中数列）。超纲解法对中学考试无效，且会误导学生。
- 不用"您"，用"你"；语气温和但准确。
- 不诊断心理、不评价人格，只说学习内容。
- 不出现"建议就医""建议咨询心理医生"等表述。
- 输出 Markdown，不要包裹代码块。"""

# D24 三态：三种「怎么讲」而不是三种「讲多少」
MODE_INSTRUCTION = {
    "direct": (
        "【直给模式】一次给出完整解答：先给答案，再给关键步骤（3-6 步），最后一句点明考点。"
        "不要反问学生，不要留悬念。"
    ),
    "analytic": (
        "【解析式模式】按步骤逐项说明，每一步写成『这一步做什么 → 依据是什么 → 得到什么』，"
        "步骤走完再给答案。重点在「为什么这么走」，不在快。"
    ),
    "guided": (
        "【引导式模式】**禁止直接给出答案**。只输出：① 一个指向关键卡点的提示（不点破）；"
        "② 一个引导问题让学生自己往下走一步；③ 一句「想好了说出来，我再往下讲」。"
        "学生回应前不要展开后续步骤。"
    ),
}

# 出域开关关闭时：只给知识点，不给题面（方案 A 的保守形态）
NO_TEXT_INSTRUCTION = (
    "【未取得题面】用户未开启题面外发，你**不会拿到题目原文**。请只基于下面给出的"
    "关联知识点，讲「这一类题怎么解」：通用思路 + 常见卡点 + 一条自检清单。"
    "明确说明这是通用解法，不要臆测具体数值或编造题目条件。"
)

WORD_CARD_TEMPLATE = """

### 📇 查词卡

| 词语 / 表达 | 释义 | 例句 | 出处 |
|---|---|---|---|
| （待填） | （待填） | （待填） | （待填） |

> 出处回溯：请注明教材版本 / 篇目 / 章节，便于回到原文核对语境。
"""

NO_ARCHIVE_MESSAGE = "这个知识点还没有讲过，点「重新讲一遍」生成第一条讲解。"


# ---------------------------------------------------------------------------
# 本地检索：题面 → 知识点候选（关键词模糊，不出域、不调云）
# ---------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    """切词：有空格按词切，中文无空格则退化为 2-gram。

    为什么要退化：中文题面通常整段无空格，``text.split()`` 会得到一整个长串，
    与知识点名做子串匹配必然 0 命中——那样「搜题结尾的知识点卡」永远是空的。
    2-gram 对「题面里出现概念名」这个主要场景够用，且纯本地、零出域。
    """
    s = "".join(ch for ch in text if not ch.isspace())
    if not s:
        return []
    # 中文无空格时 split() 得到的长串永远匹配不上知识点名，所以**同时**给 2-gram；
    # 两者取并集，拉丁文题目与中文题目都能命中。
    return [t for t in text.split() if len(t) >= 2] + [s[i:i + 2] for i in range(len(s) - 1)]


def _match_points(db: Session, text: str, subject: str | None, limit: int = 3) -> list:
    """题面文本 → 候选知识点（本地关键词模糊匹配）。

    这里刻意**不做向量召回**：题面是用户内容，`embedding_service` 对
    `EMBED_SRC_USER` 强制本地模型，pilot 阶段本地模型不一定就位；
    关键词匹配对「题面里直接出现概念名」这一主要场景已够用，且零出域风险。
    """
    q = select(KnowledgePointORM).where(KnowledgePointORM.enabled.is_(True))
    if subject:
        q = q.where(KnowledgePointORM.subject_code == subject)
    rows = db.execute(q).scalars().all()
    if not rows or not text.strip():
        return []

    tokens = _tokens(text)
    if not tokens:
        return []
    scored = []
    for p in rows:
        hay = f"{p.code} {p.name} {p.definition or ''} {(p.keywords or '')}"
        score = sum(1 for t in tokens if t in hay)
        # 至少 2 次命中才认：1 次多半是「的」「是」这类噪声 2-gram
        if score >= 2:
            scored.append((float(score) / max(len(tokens), 1), p))
    scored.sort(key=lambda x: -x[0])
    return [p for _s, p in scored[:limit]]


def _to_knowledge_ref(db: Session, user_id: str, p: KnowledgePointORM) -> KnowledgeRef:
    """知识点 → 知识引用协议卡片（含 mastery）。

    mastery 为 null = 样本不足（D48 后只有带错因的错题才喂 mastery），**不是 0**。
    库外知识（p is None 的路径）由调用方保证不进这里——它只进画像归因。
    """
    mastery: float | None = None
    try:
        inputs = gather_inputs(db, user_id, p.id)
        result = compute_mastery(p.id, inputs)
        if result.data_sufficient and result.mastery is not None:
            mastery = round(float(result.mastery), 4)
    except Exception as e:  # noqa: BLE001 — mastery 算不出来不该让搜题失败
        logger.info("[SEARCH] mastery 计算跳过: %s", type(e).__name__)

    return KnowledgeRef.model_validate({
        "pointId": p.id,
        "subjectCode": p.subject_code,
        "name": p.name,
        "mastery": mastery,
    })


def _last_mode(db: Session, user_id: str) -> str | None:
    """上次选的三态（D24 要求「可切换且被记忆」）。"""
    row = db.execute(
        select(SearchArchiveORM)
        .where(SearchArchiveORM.user_id == user_id, SearchArchiveORM.mode.is_not(None))
        .order_by(SearchArchiveORM.created_at.desc())
    ).scalars().first()
    return row.mode if row else None


def _egress_enabled(user_id: str) -> bool:
    """用户出域开关（加固 ③）。**查不到设置行 = 关闭**，默认保守。"""
    try:
        from models.user import Settings as SettingsORM

        db = SessionLocal()
        try:
            row = db.get(SettingsORM, user_id)
            return bool(row.knowledge_ai_egress_enabled) if row else False
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.info("[SEARCH] 出域开关读取失败，按关闭处理: %s", type(e).__name__)
        return False


# ---------------------------------------------------------------------------
# 出域 payload 构造：唯一允许「带上题面」的地方
# ---------------------------------------------------------------------------

def build_search_payload(
    *,
    subject: str | None,
    raw_text: str,
    refs: list[KnowledgeRef],
    egress_on: bool,
) -> tuple[str, str, dict]:
    """构造 (prompt, data_class, egress_fields)。

    **这是全模块唯一会把题面放进出域 payload 的函数**，且只在 egress_on=True
    且调用方是用户即时请求时才走 `user_error_content` 分支。
    """
    snippets = [{"pointName": r.name, "mastery": r.mastery} for r in refs]

    if egress_on:
        # 加固 ①：此分支只由 POST /search-archives 触发（无后台任务）
        fields = {"subject": subject, "rawText": raw_text}
        Guard.check(fields, USER_ERROR_CONTENT)
        prompt = (
            "题目如下：\n"
            f"---\n{raw_text}\n---\n"
            f"学科：{subject or '未指定'}\n"
            "请解这道题。"
        )
        return prompt, USER_ERROR_CONTENT, fields

    # 关闭 / 无授权：只发聚合字段，题面不出域（方案 A 的保守形态）
    fields = {
        "subject": subject,
        "retrievedFragmentSnippets": snippets,
    }
    Guard.check(fields, KNOWLEDGE_AGGREGATED)
    lines = "\n".join(f"- {r.name}" for r in refs) or "- （未匹配到知识点）"
    prompt = f"关联知识点：\n{lines}\n{NO_TEXT_INSTRUCTION}"
    return prompt, KNOWLEDGE_AGGREGATED, fields


def _needs_raw_text(mode: str) -> bool:
    """只有 direct 态必须要题面；解析式 / 引导式先走知识点聚合。

    「能走聚合就走聚合」：引导式本来就不给答案，解析式讲的是方法，
    两者都不依赖题面的具体数值。
    """
    return mode == "direct"


def _build_solution_prompt(mode: str, body: str, subject: str | None) -> str:
    tail = ""
    if subject and subject.upper() in _LANG_SUBJECTS:
        tail = WORD_CARD_TEMPLATE
    return f"{MODE_INSTRUCTION[mode]}\n\n{body}{tail}"


# ---------------------------------------------------------------------------
# POST /search-archives —— 搜题（用户即时动作）
# ---------------------------------------------------------------------------

@router.post(
    "/search-archives",
    response_model=SearchArchive,
    status_code=status.HTTP_201_CREATED,
    summary="发起搜题（三态，即时生成并归档）",
)
def create_search_archive(
    payload: SearchArchiveCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SearchArchive:
    """搜题：本地匹配知识点 → 按开关决定出域形态 → 生成 → 归档。

    ⚠️ 本函数就是「用户点击」的落地处，同步执行、无 BackgroundTasks。
    请求结束即本次授权结束，不做预生成、不做后台批量。
    """
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "rawText 不能为空", "field": "rawText"},
        )

    # D24 三态：不传就沿用上次选择（「可切换且被记忆」）
    mode = payload.mode or _last_mode(db, user.user_id) or "direct"
    if mode not in SEARCH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "mode 取值非法", "field": "mode"},
        )

    refs = [
        _to_knowledge_ref(db, user.user_id, p)
        for p in _match_points(db, raw_text, payload.subject, limit=3)
    ]

    egress_on = _egress_enabled(user.user_id) and _needs_raw_text(mode)
    prompt, data_class, egress_fields = build_search_payload(
        subject=payload.subject,
        raw_text=raw_text,
        refs=refs,
        egress_on=egress_on,
    )

    # 加固 ④：放行留痕（只记字段名清单，不抄内容）
    if data_class == USER_ERROR_CONTENT:
        log_egress_allowed(
            user_id=user.user_id,
            data_class=data_class,
            scene="search_solution",
            keys=egress_fields.keys(),
            note=f"mode={mode}",
        )

    text = None
    try:
        from llm_provider import get_provider

        provider = get_provider()
        text = provider.generate(
            _build_solution_prompt(mode, prompt, payload.subject),
            context={
                "system": SOLUTION_SYSTEM,
                "scene": "search_solution",
                "subject": payload.subject,
                "egress_fields": egress_fields,
                "data_class": data_class,
                "user_id": user.user_id,
                "feature_tier": "embedded",
            },
        )
        if text:
            from safety_filter import check

            passed, reason = check(text)
            if not passed:
                logger.warning("[SEARCH] 审核拦截: %s", reason)
                text = None
    except Exception as e:  # noqa: BLE001
        logger.warning("[SEARCH] 生成失败，走降级: %s: %s", type(e).__name__, e)

    solution = (text or "").strip() or _fallback_solution(mode)

    # D52 多解：MVP 只产主解；solutions 先只放主解，count 供前端分页位
    solutions = [solution][:_MAX_SOLUTIONS]

    now = datetime.now(timezone.utc)
    row = SearchArchiveORM(
        id=f"sa_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        subject=payload.subject,
        raw_text=raw_text,
        solution=solution,
        mode=mode,
        point_ids=json.dumps([r.model_dump(by_alias=True, exclude_none=True) for r in refs],
                             ensure_ascii=False),
        created_at=now,
    )
    db.add(row)
    db.commit()

    return SearchArchive.model_validate({
        "archiveId": row.id,
        "subject": row.subject,
        "rawText": row.raw_text,
        "solution": row.solution,
        "mode": row.mode,
        "pointIds": [r.model_dump(by_alias=True, exclude_none=True) for r in refs],
        "solutions": solutions,
        "solutionCount": len(solutions),
        "createdAt": now.isoformat(),
    })


def _fallback_solution(mode: str) -> str:
    """降级文案（模型不可用时前端也拿得到内容）。"""
    if mode == "guided":
        return (
            "### 🧭 先自己走一步\n"
            "1. 先看清题目要求的是什么——是求值、证明，还是判断？\n"
            "2. 想好了说出来，我再往下讲。"
        )
    if mode == "analytic":
        return (
            "### 🔍 分步解析\n"
            "1. 识别考查的核心知识点\n"
            "2. 写出对应定义与公式\n"
            "3. 逐项代入条件并化简\n"
            "4. 检查每一步的依据是否成立"
        )
    return (
        "### 💡 解答\n"
        "1. 先识别题目考查的核心知识点\n"
        "2. 写出定义与公式，逐项代入\n"
        "3. 检查单位、定义域与前提条件\n\n"
        "（本次未能生成针对这道题的完整解答，以上为通用解法，可点「重新生成」再试）"
    )


# ---------------------------------------------------------------------------
# GET /search-archives —— 归档列表 / 详情
# ---------------------------------------------------------------------------

def _archive_to_item(row: SearchArchiveORM) -> dict:
    try:
        refs = json.loads(row.point_ids) if row.point_ids else []
    except (ValueError, TypeError):
        refs = []
    return {
        "archiveId": row.id,
        "subject": row.subject,
        "rawText": row.raw_text,
        "solution": row.solution,
        "mode": row.mode,
        "pointIds": refs,
        "solutions": ([row.solution] if row.solution else [])[:_MAX_SOLUTIONS],
        "solutionCount": 1 if row.solution else 0,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


@router.get(
    "/search-archives",
    response_model=SearchArchiveList,
    summary="搜题归档列表（可按学科 / 三态过滤）",
)
def list_search_archives(
    subject: str | None = None,
    mode: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SearchArchiveList:
    if mode is not None and mode not in SEARCH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "mode 取值非法", "field": "mode"},
        )
    q = select(SearchArchiveORM).where(SearchArchiveORM.user_id == user.user_id)
    if subject:
        q = q.where(SearchArchiveORM.subject == subject)
    if mode:
        q = q.where(SearchArchiveORM.mode == mode)
    total = db.execute(
        select(SearchArchiveORM.id).where(SearchArchiveORM.user_id == user.user_id)
    ).all()
    rows = db.execute(
        q.order_by(SearchArchiveORM.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return SearchArchiveList(
        items=[SearchArchive.model_validate(_archive_to_item(r)) for r in rows],
        pagination={"total": len(total), "limit": limit, "offset": offset},
    )


@router.get(
    "/search-archives/{archive_id}",
    response_model=SearchArchive,
    summary="搜题归档详情",
)
def get_search_archive(
    archive_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SearchArchive:
    row = db.get(SearchArchiveORM, archive_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "归档不存在"},
        )
    return SearchArchive.model_validate(_archive_to_item(row))


# ---------------------------------------------------------------------------
# /explanations —— 讲解归档（D52）
# ---------------------------------------------------------------------------

EXPLANATION_SYSTEM = """你是一个中学学科教师，要讲透一个知识点。

硬约束：
- **只允许使用中学（初中/高中）课程标准内的方法与例子**，不引入超纲内容。
- 结构：① 一句话说清这是什么 ② 一个具体例子 ③ 一个常见易错点 ④ 一道自检小问。
- 不用"您"，用"你"；不诊断心理、不评价人格。
- 300 字以内，Markdown，不要代码块。"""


def _expl_to_item(row: ExplanationORM) -> dict:
    return {
        "explanationId": row.id,
        "pointId": row.point_id,
        "subject": row.subject,
        "mode": row.mode,
        "content": row.content,
        "isCurated": row.is_curated,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


@router.post(
    "/explanations",
    response_model=Explanation,
    status_code=status.HTTP_201_CREATED,
    summary="讲解：回顾取原文（original）/ 重新讲现生成（regenerated）",
)
def create_explanation(
    payload: ExplanationCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Explanation:
    """D52：两态并存——`original` 取回上次那条（不调模型），`regenerated` 现生成一条。

    重生成保证不了一致性，而讲解的价值恰恰在「上次那个讲法、那个例子」，
    所以**不用新的一条顶掉旧的**，两条都留在归档里。
    """
    if payload.point_id is None and payload.subject is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "pointId 与 subject 至少要有一个",
                "field": "pointId",
            },
        )

    # original：回顾取原文。取该用户该知识点最近一条，不调模型。
    if payload.mode == "original":
        q = select(ExplanationORM).where(ExplanationORM.user_id == user.user_id)
        if payload.point_id:
            q = q.where(ExplanationORM.point_id == payload.point_id)
        row = db.execute(q.order_by(ExplanationORM.created_at.desc())).scalars().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": NO_ARCHIVE_MESSAGE},
            )
        # 取回不是新建：返回 200，与 regenerated 的 201 区分开
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=Explanation.model_validate(_expl_to_item(row)).model_dump(
                by_alias=True, exclude_none=False
            ),
        )

    # regenerated：现生成
    point_name = None
    if payload.point_id:
        p = db.get(KnowledgePointORM, payload.point_id)
        if p is not None:
            point_name = p.name

    prompt = (
        f"知识点：{point_name or '（未指定）'}\n"
        f"学科：{payload.subject or '未指定'}\n"
        "请把这个知识点讲透。"
    )
    # 讲解**只走聚合**：讲概念不需要题面，不碰 user_error_content
    egress_fields = {"subject": payload.subject, "pointName": point_name}
    Guard.check(egress_fields, KNOWLEDGE_AGGREGATED)

    text = None
    try:
        from llm_provider import get_provider

        provider = get_provider()
        text = provider.generate(
            prompt,
            context={
                "system": EXPLANATION_SYSTEM,
                "scene": "explanation",
                "subject": payload.subject,
                "egress_fields": egress_fields,
                "data_class": KNOWLEDGE_AGGREGATED,
                "user_id": user.user_id,
                "feature_tier": "embedded",
            },
        )
        if text:
            from safety_filter import check

            passed, reason = check(text)
            if not passed:
                logger.warning("[EXPLANATION] 审核拦截: %s", reason)
                text = None
    except Exception as e:  # noqa: BLE001
        logger.warning("[EXPLANATION] 生成失败，走降级: %s: %s", type(e).__name__, e)

    content = (text or "").strip() or (
        "### 📖 讲解\n"
        "1. 先记住定义：它是什么、成立的前提是什么\n"
        "2. 看一个最标准的例题，跟着走一遍\n"
        "3. 记住那个最容易踩的坑\n\n"
        "（本次未能生成定制讲解，以上为通用结构，可再点一次「重新讲一遍」）"
    )

    now = datetime.now(timezone.utc)
    row = ExplanationORM(
        id=f"exp_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        point_id=payload.point_id,
        subject=payload.subject,
        mode="regenerated",
        content=content,
        is_curated=False,
        created_at=now,
    )
    db.add(row)
    db.commit()

    return Explanation.model_validate(_expl_to_item(row))


@router.get(
    "/explanations",
    response_model=ExplanationList,
    summary="讲解归档列表（可按知识点 / 精品标记过滤）",
)
def list_explanations(
    point_id: str | None = Query(None, alias="pointId"),
    subject: str | None = None,
    is_curated: bool | None = Query(None, alias="isCurated"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ExplanationList:
    """列表。**精品样例（isCurated=true）与动态生成严格区分**，前端靠该字段分开展示。

    精品样例由 `scripts/seed_curated_explanations.py` 预制入库（pilot 3–5 个），
    长期保存；动态生成的是 `isCurated=false`。
    """
    q = select(ExplanationORM).where(ExplanationORM.user_id == user.user_id)
    if point_id:
        q = q.where(ExplanationORM.point_id == point_id)
    if subject:
        q = q.where(ExplanationORM.subject == subject)
    if is_curated is not None:
        q = q.where(ExplanationORM.is_curated.is_(is_curated))
    rows = db.execute(
        q.order_by(ExplanationORM.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    total = db.execute(
        select(ExplanationORM.id).where(ExplanationORM.user_id == user.user_id)
    ).all()
    return ExplanationList(
        items=[Explanation.model_validate(_expl_to_item(r)) for r in rows],
        pagination={"total": len(total), "limit": limit, "offset": offset},
    )


@router.get(
    "/explanations/{explanation_id}",
    response_model=Explanation,
    summary="讲解详情",
)
def get_explanation(
    explanation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Explanation:
    row = db.get(ExplanationORM, explanation_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "讲解不存在"},
        )
    return Explanation.model_validate(_expl_to_item(row))

"""Chat 内核编排层（B 板块 M1 最小真链路）。

职责：意图管道 → 上下文栈 → 画像按意图注入 → LLM → 情绪安全/危机 → usage_ledger 留痕。
不含 HTTP 逻辑（在 routes/chat.py）。

最小真链路范围（本批交付）：
- 单轮真实问答：调 llm_provider，失败/被审走温和兜底
- 意图三通道（D3）：斜杠命令 / 按钮（显式 intent）/ 模型裸判（返回 None 交模型）
- 单对话 + 上下文栈（D2/D36）：深度=3、LIFO、会话级；超限最旧者「沉降」留痕
- 危机信号 L3 转介（D37）：确定性前置检查，不过 LLM，事件细节绝不进画像
- 画像四组按意图选组注入（D50 读侧）：只读 user_profiles，不全量注入
- usage_ledger 数值流水：token 估算、cost 暂记 0（pilot 定价后置）

显式延后（见 handoff / 契约）：
- 划选两条路径（D51）、常用语（D23）、语言风格写画像（#20）→ M2
- 画像「模型隐式提取写入」（D50 写侧）、话题摘要生成（#34）→ M1 后续
- 多产物结构化卡片解析 → M1 后续（响应已预留 cards 字段）
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from llm_provider import get_provider
from models.chat import ChatRawMessage, ChatSession, TopicSummary, UserProfile
from models.governance import UsageLedger
from privacy_filter import sanitize_text
from safety_filter import CRISIS_RESPONSE, check as safety_check, is_crisis_signal
from schemas.chat import ChatCard, ChatReply

logger = logging.getLogger(__name__)

# ---------- 常量（口径集中在配置或此常量区，不散落在各调用点） ----------
STACK_DEPTH = 3        # 上下文栈深度（D36）
RAW_TTL_DAYS = 30      # 对话原文留存窗口（§3.8.3）
SESSION_AGING_DAYS = 7  # 会话老化阈值（§3.8.1）
MAX_RECENT_TURNS = 6    # 供模型衔接的最近轮次（不是历史列表）

# #34 跨登录话题摘要：离开 AI 页超过该时长视为「会话结束」的冷启动，
# 冷启动时才从保留原文按需生成摘要（短离开跳过，不按每次切页生成）。
SUMMARY_IDLE_HOURS = 12

# 问候语骨架（§1.3「预设骨架 + 动态填充」：摘要只填进 AGAIN 的 {summary}）
_GREETING_FIRST = "嗨，我是你的 AI 学习助手。今天想从哪开始？"
_GREETING_REOPEN = "好久不见，欢迎回来。接着上次的继续，还是换个新目标？"
_GREETING_SHORT = "我又回来啦。接着刚才的继续，还是想聊点别的？"
_GREETING_AGAIN = "好久不见！上次我们聊到：{summary}。今天想学点什么？"

# 画像四组（D50）。组名与 user_profiles.profile_group 对齐。
_PROFILE_GROUPS = ("learning", "state", "attribution", "interest")

_KNOWN_INTENTS = {"chat", "search", "explain", "practice", "task", "goal", "question", "emotional"}

# 斜杠命令 → 意图（D3 第一通道）。与 chat_system.txt 的斜杠命令对齐。
_SLASH_INTENTS = {
    "/搜题": "search",
    "/查": "search",
    "/讲知识点": "explain",
    "/讲题": "explain",
    "/讲": "explain",
    "/出题": "practice",
    "/练": "practice",
    "/计划": "task",
    "/建任务": "task",
    "/目标": "goal",
    "/问": "question",
}

# 意图 → 注入的画像组（D50：按意图选组，不全量注入）
_INTENT_PROFILE_GROUPS: dict[str, list[str]] = {
    "search": ["learning", "attribution"],
    "explain": ["learning", "attribution"],
    "practice": ["learning", "attribution"],
    "question": ["learning", "attribution"],
    "task": ["learning", "state"],
    "goal": ["learning", "state"],
    "emotional": ["state"],
    "chat": ["interest"],
}

_FALLBACK_REPLY = "我暂时接不上你的话，能换个说法再跟我说一次吗？"

# 知识帮助类意图：命中时先检索知识点库，把真实 pointId 注入，供出「知识点卡」引用
_KNOWLEDGE_INTENTS = {"search", "explain", "practice", "question"}

# 专注动作确定性兜底：中文学科词 → 学科码（与 schemas.enums.Subject 对齐）
_STUDY_SUBJECT_MAP = {
    "数学": "SX", "英语": "YY", "英文": "YY", "物理": "WL", "化学": "HX",
    "语文": "YW", "历史": "LS", "地理": "DL", "政治": "ZZ", "生物": "SW",
}
# 动作触发词：命中的才走确定性兜底，避免把普通聊天误判成「开始专注」
_STUDY_ACTION_RE = re.compile(r"专注|番茄钟|背书|背单词|背诵|刷题|做题|自习|想学|开始学|学一下|学一会|学一会儿|复习|写作业|预习")
# 时长：如「20分钟」「30 分」「25min」（10–600 收口）
_STUDY_MINUTES_RE = re.compile(r"(\d{1,3})\s*(?:分钟|分|min(?:utes?)?)", re.IGNORECASE)
# 任务方向：从用户原话抽具体学习动作，让计时页任务文案对接用户输入而非学科模板
_STUDY_DIRECTION_MAP = {
    "背单词": "背单词", "背书": "背书", "背诵": "背书",
    "刷题": "刷题", "做题": "刷题",
    "复习": "复习", "预习": "预习",
    "写作业": "写作业", "做作业": "写作业",
}


def _gen(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.utcnow()


def _now_iso() -> str:
    # 栈项 enteredAt 用 ISO 串（避免 naive datetime 序列化歧义）
    return _utcnow().isoformat()


# ---------- 意图管道（D3） ----------

def detect_intent(content: str, explicit_intent: str | None = None) -> str | None:
    """三通道合成：显式按钮 > 斜杠命令 > 模型裸判（返回 None）。

    斜杠/按钮得到确定意图；裸判返回 None，由模型依据 system prompt 自行判定。
    """
    if explicit_intent and explicit_intent in _KNOWN_INTENTS:
        return explicit_intent
    stripped = (content or "").strip()
    if stripped.startswith("/"):
        cmd = stripped.split(maxsplit=1)[0]
        return _SLASH_INTENTS.get(cmd)
    return None


def _intent_to_profile_groups(intent: str | None) -> list[str]:
    if intent in _INTENT_PROFILE_GROUPS:
        return _INTENT_PROFILE_GROUPS[intent]
    # 裸判 / 未知：注入覆盖面最广的两组（学习 + 状态），最安全
    return ["learning", "state"]


def _intent_to_branch_type(intent: str | None) -> str:
    if intent in ("task", "goal"):
        return "task_draft"
    if intent in ("search", "explain", "practice", "question"):
        return "knowledge_help"
    return "chat"


# ---------- 会话与上下文栈（D2 / D36） ----------

def _get_or_create_session(db: Session, user_id: str) -> ChatSession:
    session = db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.last_active_at.desc(), ChatSession.id.desc())
        .limit(1)
    ).scalars().first()

    now = _utcnow()
    if session is None:
        session = ChatSession(id=_gen("cs"), user_id=user_id, context_stack_json=None)
        db.add(session)
        db.flush()
        return session

    # 老化：超过阈值清空栈内上下文（沉降物不随会话老化，各走各的 TTL）
    if session.last_active_at is not None and (
        now - session.last_active_at
    ) > timedelta(days=SESSION_AGING_DAYS):
        session.context_stack_json = None
    return session


def _load_stack(session: ChatSession) -> list[dict]:
    if not session.context_stack_json:
        return []
    try:
        data = json.loads(session.context_stack_json)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        logger.warning("[CHAT] 上下文栈 JSON 解析失败，重置为空")
    return []


def _push_branch(stack: list[dict], branch_type: str, intent: str | None) -> list[dict]:
    """压栈（LIFO：栈顶 = 最近）。超限最旧者沉降留痕。"""
    stack.append({
        "branchType": branch_type,
        "intent": intent,
        "step": None,
        "payload": None,
        "enteredAt": _now_iso(),
    })
    while len(stack) > STACK_DEPTH:
        dropped = stack.pop(0)
        logger.info(
            "[CHAT] 上下文栈超限，沉降最旧分支 branchType=%s intent=%s",
            dropped.get("branchType"), dropped.get("intent"),
        )
    return stack


# ---------- 画像注入（D50 读侧） ----------

def _load_profile(db: Session, user_id: str, groups: list[str]) -> list[UserProfile]:
    rows = db.execute(
        select(UserProfile)
        .where(
            UserProfile.user_id == user_id,
            UserProfile.profile_group.in_(groups),
        )
        .order_by(UserProfile.profile_group, UserProfile.updated_at.desc())
    ).scalars().all()
    return list(rows)


def _format_profile(rows: list[UserProfile]) -> str:
    if not rows:
        return "# 关于这个学生，你已知的画像（按意图注入的相关组）\n（暂无相关画像）"
    grouped: dict[str, list[UserProfile]] = {}
    for r in rows:
        grouped.setdefault(r.profile_group, []).append(r)
    lines = ["# 关于这个学生，你已知的画像（只注入与当前意图相关的组，不要编造新的）"]
    for grp in _PROFILE_GROUPS:
        if grp not in grouped:
            continue
        lines.append(f"[{grp}]")
        for e in grouped[grp]:
            lines.append(f"- {e.key}：{e.value}")
    return "\n".join(lines)


# ---------- 语言风格（#20：画像字段，全量注入，变更必告知） ----------

# 风格画像条目的合法 key（chat_system.txt 用 interest/style；语义别名 语言风格 也兼容）
_STYLE_KEYS = ("style", "语言风格")


def _load_style(db: Session, user_id: str) -> str | None:
    """读该学生的语言风格（user_profiles 里 key 为 style/语言风格）。风格独立于意图组，需**全量**注入。"""
    row = db.execute(
        select(UserProfile)
        .where(UserProfile.user_id == user_id, UserProfile.key.in_(_STYLE_KEYS))
        .order_by(UserProfile.updated_at.desc())
        .limit(1)
    ).scalars().first()
    return row.value if row is not None else None


def _format_style(value: str | None) -> str:
    if not value:
        return "# 语言风格\n（保持自然、亲切、简洁的中文，不啰嗦）"
    return f"# 语言风格（用户明确要求，务必严格遵守；若不清晰请先追问确认）\n{value}"


def _format_stack(stack: list[dict]) -> str:
    if not stack:
        return "# 上下文栈\n（空）"
    lines = ["# 上下文栈（聊到一半的分支；栈顶=最近，切回时可自然承接）"]
    for item in reversed(stack):
        lines.append(f"- [{item.get('branchType')}] intent={item.get('intent')} step={item.get('step')}")
    return "\n".join(lines)


# ---------- prompt 组装 ----------

def _load_file(filename: str) -> str:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "prompts", filename), encoding="utf-8") as f:
        return f.read()


def _load_chat_system() -> str:
    """读 chat_system.txt，取 SYSTEM 段作为系统提示词基线（内含 #17/#24/D37 硬约束）。"""
    import re
    text = _load_file("chat_system.txt")
    sys_match = re.search(r"(?m)^#?\s*SYSTEM\s*:\s*$", text)
    user_match = re.search(r"(?m)^#?\s*USER\s*:\s*$", text)
    if not sys_match or not user_match or user_match.start() <= sys_match.end():
        raise ValueError("chat_system.txt 缺少合法的 SYSTEM/USER 分段标记")
    return text[sys_match.end():user_match.start()].strip()


def _build_system_prompt(profile_rows: list[UserProfile], stack: list[dict]) -> str:
    return "\n\n".join([
        _load_chat_system(),
        _format_profile(profile_rows),
        _format_stack(stack),
    ])


def _load_recent_messages(db: Session, user_id: str, session_id: str) -> list[tuple[str, str]]:
    rows = db.execute(
        select(ChatRawMessage)
        .where(
            ChatRawMessage.user_id == user_id,
            ChatRawMessage.session_id == session_id,
        )
        .order_by(ChatRawMessage.created_at.desc(), ChatRawMessage.id.desc())
        .limit(MAX_RECENT_TURNS)
    ).scalars().all()
    return [(r.role, r.content) for r in reversed(rows)]


def _build_user_prompt(recent: list[tuple[str, str]], content: str, intent: str | None) -> str:
    lines: list[str] = []
    if recent:
        lines.append("# 最近这几轮对话（仅用于衔接上下文，不是历史记录，不要主动复述给用户）")
        for role, text in recent:
            who = "用户" if role == "user" else "助手"
            lines.append(f"{who}：{text}")
    lines.append("# 本轮消息")
    lines.append(content)
    if intent:
        lines.append(f"（已判定意图：{intent}）")
    return "\n".join(lines)


# ---------- 输出与安全 ----------

# 卡片 JSON 的 fenced code block（模型按 chat_system.txt 协议在回复末尾输出）
_CARD_FENCE_RE = re.compile(r"```(?:json)?[ \t]*\n(.*?)```", re.DOTALL)

# 画像增量 JSON 的 fenced code block（D50 写侧，```profile）
_PROFILE_FENCE_RE = re.compile(r"```profile[ \t]*\n(.*?)```", re.DOTALL)

# 剥离所有 fenced code block（卡片 JSON + profile JSON），剩纯文本给人看
_ALL_FENCE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)

# 剥离卡片块后若文本为空，用这句回退（避免只回一张卡、没有半句人话）
_CARD_ONLY_REPLY = "已为你准备好，点下面的卡片开始吧。"


def _parse_cards(llm_text: str) -> list[ChatCard]:
    """容错解析回复里夹带的结构化卡片 JSON（D22）。

    支持单卡片对象或卡片数组；任一张解析失败都不影响其余与自由文本——
    Chat 永不因模型格式漂移而 500。
    """
    cards: list[ChatCard] = []
    for m in _CARD_FENCE_RE.finditer(llm_text):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[CHAT] 卡片 JSON 解析失败，忽略该块")
            continue
        items = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict) or not item.get("type"):
                continue
            try:
                cards.append(ChatCard.model_validate(item))
            except Exception as e:  # noqa: BLE001 — 单张卡校验失败不影响其它
                logger.warning("[CHAT] 卡片校验失败: %s", e)
    return cards


def _resolve_reply(llm_text: str | None) -> tuple[str, list, bool]:
    if not llm_text:
        return _FALLBACK_REPLY, [], True
    passed, reason = safety_check(llm_text)
    if not passed:
        logger.warning("[CHAT] LLM 输出被安全审核拦截: %s", reason)
        return _FALLBACK_REPLY, [], True
    cards = _parse_cards(llm_text)
    # 剥离所有 fenced 块（卡片 + 画像），剩余文本即给人看的话；剥空了就用固定回退句
    reply = _ALL_FENCE_RE.sub("", llm_text).strip() or _CARD_ONLY_REPLY
    return reply, cards, False


def _parse_profile_increments(llm_text: str | None) -> list[dict]:
    """解析回复里夹带的画像增量 JSON（D50 写侧）。

    模型按协议在 ```profile 块里给 {items:[{group,key,value}]}。事件细节不入画像
    由 chat_system.txt 约束，这里再按四组合法 group 取值双重把关。
    """
    increments: list[dict] = []
    for m in _PROFILE_FENCE_RE.finditer(llm_text or ""):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[CHAT] 画像 JSON 解析失败，忽略")
            continue
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            group = str(it.get("group", "")).strip()
            key = str(it.get("key", "")).strip()
            value = str(it.get("value", "")).strip()
            if group not in _PROFILE_GROUPS or not key or not value:
                continue
            increments.append({"group": group, "key": key, "value": value})
    return increments


def _upsert_profile_increments(db: Session, user_id: str, items: list[dict]) -> None:
    """画像增量落库：同 (user, group, key) 覆盖 value，不新增重复（UniqueConstraint）。"""
    if not items:
        return
    added = 0
    for it in items:
        existing = db.execute(
            select(UserProfile).where(
                UserProfile.user_id == user_id,
                UserProfile.profile_group == it["group"],
                UserProfile.key == it["key"],
            )
        ).scalars().first()
        if existing is not None:
            existing.value = it["value"]
            existing.source = "inferred"
        else:
            db.add(UserProfile(
                id=_gen("up"),
                user_id=user_id,
                profile_group=it["group"],
                key=it["key"],
                value=it["value"],
                source="inferred",
            ))
            added += 1
    logger.info("[CHAT] 画像写侧：新增 %d 条 / 覆盖 %d 条", added, len(items) - added)


def _retrieve_knowledge_points(db: Session, text: str, limit: int = 3) -> list[dict]:
    """从知识点库检索候选（name_fuzzy 关键词匹配，embedding off 时够用）。

    返回真实 {pointId,name,subjectCode}，供注入 prompt 出「知识点卡」——#9 只许用真 pointId。
    """
    from models.knowledge import KnowledgePoint

    q = select(KnowledgePoint).where(KnowledgePoint.enabled.is_(True))
    rows = db.execute(q).scalars().all()

    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
    scored: list[tuple[int, KnowledgePoint]] = []
    for p in rows:
        hay = f"{p.code} {p.name} {p.definition or ''}"
        score = sum(1 for t in tokens if t in hay)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [
        {"pointId": p.id, "name": p.name, "subjectCode": p.subject_code}
        for _, p in scored[:limit]
    ]


def _format_knowledge_for_prompt(knowledge: list[dict]) -> str:
    """把检索到的知识点格式化成 prompt 片段，约束模型只用这些真 pointId 出卡。"""
    if not knowledge:
        return ""
    lines = ["\n# 相关知识点（出「知识点卡」只能引用下面这些真实 pointId，不得编造）"]
    for k in knowledge:
        lines.append(f"- [{k['pointId']}] {k['name']}")
    return "\n".join(lines)


def _load_goals_context(db: Session, user_id: str) -> str:
    """把该学生的目标清单（含归档）注入 prompt——否则模型看不到有哪些目标，
    删目标/更新目标时只能回问、编出没标题的空卡（#17 防破甲 / 前置可查）。"""
    from models.goal import Goal as GoalORM

    rows = db.execute(
        select(GoalORM)
        .where(GoalORM.user_id == user_id)
        .order_by(GoalORM.status.asc(), GoalORM.created_at.asc())
    ).scalars().all()
    if not rows:
        return ""
    lines = ["\n# 该学生当前的目标清单（含已归档；这里是**唯一可靠**的目标来源，删除/更新务必引用真实 title/subject，绝不猜测）"]
    for g in rows:
        st = "进行中" if g.status == "active" else "已归档"
        lines.append(f"- [{st}] {g.title}（学科={g.subject}，{g.type}）")
    lines.append("\n删除目标时遵循：若用户说「删某个已归档目标/任务」但没指明学科或标题，"
                 "**先看清单里已归档的目标**——只有一个就直接用它生成删除确认卡；有多个则列出让用户选，"
                 "**不要自己猜学科**（如默认数学/地理）。")
    return "\n".join(lines)


def _extract_study_card(content: str) -> ChatCard | None:
    """确定性兜底：从用户原话抽「学科 + 时长」构造专注确认卡。

    模型出卡不稳定 / 漏 goal（学科）时，靠它保证「开始专注类」诉求
    也能稳定把 subject 传给前端建目标 + 生成对应学科的计划——这是
    「学科/任务对上」的兜底，不再依赖模型是否按协议输出卡片。
    """
    text = (content or "").strip()
    if not _STUDY_ACTION_RE.search(text):
        return None

    subject_code: str | None = None
    subject_cn: str | None = None
    for cn, code in _STUDY_SUBJECT_MAP.items():
        if cn in text:
            subject_code = code
            subject_cn = cn
            break

    m = _STUDY_MINUTES_RE.search(text)
    minutes = int(m.group(1)) if m else None

    # 任务方向：命中「背书/刷题/复习…」才够具体，能作为任务文案
    direction = None
    for kw, label in _STUDY_DIRECTION_MAP.items():
        if kw in text:
            direction = label
            break
    # 专注类动作：只有「专注/自习/番茄钟」这类明确的开始动作才允许「通用专注」内容
    is_focus = bool(re.search(r"专注|自习|番茄钟", text))

    # 先问清楚再给卡（#17 / D53 别替用户做决定）：只说「想学地理/学一会儿」而未定内容时，
    # **不产卡、不默认任何内容**（如「基础知识点复习」），交回模型先追问学哪个方向。
    # 有具体方向；或明确时长 + 专注动作 → 才出开始卡。
    if direction is None and not (is_focus and minutes is not None):
        return None
    # 学科、时长至少要有一个，否则不值得出卡
    if subject_code is None and minutes is None:
        return None

    if subject_code is None:
        subject_code = "other"
        subject_cn = "综合"
    minutes = min(600, max(10, minutes or 25))

    if direction:
        task_text = f"{subject_cn} · {direction}"
    elif subject_code != "other":
        task_text = f"{subject_cn} · 专注学习"
    else:
        task_text = "专注学习"

    summary = f"为你安排：{task_text}（{minutes} 分钟）"
    return ChatCard(
        type="confirmation",
        title="准备好就开始",
        display={
            "summary": summary,
            "items": [
                {"label": "学科", "value": subject_cn},
                {"label": "任务", "value": task_text},
                {"label": "时长", "value": f"{minutes} 分钟"},
            ],
        },
        payload={
            "goal": {"subject": subject_code, "title": f"{subject_cn}学习", "description": ""},
            "plan": {"availableMinutes": minutes},
            "task": task_text,
        },
    )


def _is_start_card(c: ChatCard) -> bool:
    """判定是否为「开始学习」类确认卡（无论模型给没给 action，看 goal/plan/task）。"""
    if c.type != "confirmation":
        return False
    p = c.payload or {}
    if p.get("action") == "start_study":
        return True
    return bool(p.get("goal") or p.get("plan") or p.get("task"))


def _is_vague_study_request(content: str) -> bool:
    """模糊学习请求：提到学习但**没说具体方向/内容**，也未给「专注+时长」。
    这类请求应只追问方向、**绝不出开始学习卡**（也不默认内容）——与 _extract_study_card 的门槛一致。
    """
    if not _STUDY_ACTION_RE.search(content):
        return False
    if any(kw in content for kw in _STUDY_DIRECTION_MAP):
        return False
    if re.search(r"专注|自习|番茄钟", content) and _STUDY_MINUTES_RE.search(content):
        return False  # 明确「专注+时长」不算模糊
    return True


# 删除目标的确定性兜底（#17 防破甲）：模型若不出卡、或空转问「你要删哪个」，
# 由规则从用户原话识别「删除已归档目标」，命中唯一已归档目标时直接产删除确认卡。
_DELETE_RE = re.compile(r"删(?:除|掉|一下|了)?|移除|清掉")
_ARCHIVED_RE = re.compile(r"已归档|归档|已完成的|已完成|完成的目标|旧目标")


def _extract_delete_card(db: Session, user_id: str, content: str) -> ChatCard | None:
    """确定性兜底：用户要删「已归档目标」且只有**一个**已归档目标 → 产删除确认卡。

    只有「明确是删除 + 明确提到归档 + 且只剩唯一归档目标」才触发，避免猜错目标；
    多个归档 / 没提归档 → 交回模型（本轮不强行出卡）。
    """
    if not _DELETE_RE.search(content) or not _ARCHIVED_RE.search(content):
        return None
    from models.goal import Goal as GoalORM

    archived = db.execute(
        select(GoalORM)
        .where(GoalORM.user_id == user_id, GoalORM.status == "archived")
        .order_by(GoalORM.created_at.asc())
    ).scalars().all()
    if len(archived) != 1:
        return None
    g = archived[0]
    return ChatCard(
        type="confirmation",
        title="确认删除已归档目标",
        display={
            "summary": f"将删除已归档目标「{g.title}」",
            "items": [
                {"label": "目标", "value": g.title},
                {"label": "学科", "value": g.subject},
                {"label": "状态", "value": "已归档"},
            ],
        },
        payload={"action": "delete_goal", "goal": {"subject": g.subject, "title": g.title}},
    )


# ---------- 持久化与留痕 ----------

def _persist_raw(db: Session, user_id: str, session_id: str, role: str, content: str) -> None:
    db.add(ChatRawMessage(
        id=_gen("msg"),
        user_id=user_id,
        session_id=session_id,
        role=role,
        content=content,
        expires_at=_utcnow() + timedelta(days=RAW_TTL_DAYS),
    ))


def _record_usage(db: Session, user_id: str, prompt: str, reply: str) -> None:
    """写 usage_ledger 数值流水（G 后续收敛到 llm_provider 出口）。

    token 估算（provider 不返回 usage）；cost 暂记 0 —— pilot 不收费、定价后置。
    """
    db.add(UsageLedger(
        id=_gen("usage"),
        user_id=user_id,
        feature_tier="chat",
        reasoning_tier="standard",
        model=settings.llm_model or "unknown",
        tokens_in=max(1, len(prompt) // 4),
        tokens_out=max(1, len(reply) // 4),
        cost=0.0,
    ))


# ---------- 主流程 ----------

def _latest_session(db: Session, user_id: str) -> ChatSession | None:
    return db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.last_active_at.desc())
        .limit(1)
    ).scalars().first()


def _summarize_previous_period(
    db: Session, user_id: str, session_id: str, boundary: datetime,
) -> str | None:
    """从保留原文（上一段使用周期，早于 boundary、TTL 内）提炼 2-3 条话题摘要。

    仅在冷启动（离开 > SUMMARY_IDLE_HOURS）时按需生成；失败静默返回 None，
    不影响问候语（回落骨架），聊天绝不因摘要失败而 500。
    """
    msgs = db.execute(
        select(ChatRawMessage)
        .where(
            ChatRawMessage.user_id == user_id,
            ChatRawMessage.session_id == session_id,
            ChatRawMessage.created_at < boundary,
        )
        .order_by(ChatRawMessage.created_at.asc())
    ).scalars().all()
    if not msgs:
        return None
    transcript = "\n".join(
        f"{'用户' if m.role == 'user' else '助手'}：{m.content}"
        for m in msgs[-40:]
    )
    prompt = (
        "下面是这位学生上一段 AI 辅导对话的部分原文。请用中文提炼 **2-3 条结构化话题摘要**，"
        "每条一句话，聚焦「上次聊到了什么 / 卡在了哪里 / 有没有留下待办」。"
        "只输出摘要条目，不要客套、不要复述原文、不要代码块。\n\n"
        f"---\n{transcript}\n---\n输出："
    )
    try:
        # ⚠️ data_class 必须显式声明：未声明时 provider 层按「历史调用」直接放行、
        # 出域白名单一律不校验（tests/test_egress_ci.py 守这条）。
        # 这里送出去的是**学生自己在对话里说过的原文**——按 egress_guard 的判定规则
        # 「不看存没存过，看是不是用户主动发起 + 内容是不是用户自己的」，
        # 归 user_error_content（用户内容类），不是 knowledge_raw（后者永不出域）。
        # 用字面量而非 egress_guard.USER_ERROR_CONTENT：CI（test_egress_ci.py）
        # 是静态扫描源码文本的，常量变量会被判为「动态值、无法判定」。
        # 改动此值时必须与 egress_guard.USER_ERROR_CONTENT 同步。
        out = get_provider().generate(
            prompt,
            context={"scene": "chat_topic_summary", "data_class": "user_error_content"},
        )
    except Exception as e:  # noqa: BLE001 — 摘要失败不阻断问候/聊天
        logger.warning("[CHAT] 话题摘要生成失败: %s", e)
        return None
    if not out:
        return None
    clean = _ALL_FENCE_RE.sub("", out).strip()
    return clean[:500] or None


def _save_topic_summary(db: Session, user_id: str, session_id: str, summary: str) -> None:
    """只保留最近一次「上次聊到」摘要，避免无限累积。"""
    for old in db.execute(
        select(TopicSummary).where(TopicSummary.user_id == user_id)
    ).scalars().all():
        db.delete(old)
    db.add(TopicSummary(
        id=_gen("ts"),
        user_id=user_id,
        session_id=session_id,
        summary=summary,
    ))
    db.commit()
    logger.info("[CHAT] 话题摘要已写入 user=%s", user_id)


def greeting(db: Session, user_id: str) -> dict:
    """回到 AI 页的问候语（#34）。冷启动（距上次交互 > SUMMARY_IDLE_HOURS）时
    从保留原文生成摘要并落库 topic_summaries，填进问候语骨架；短离开不生成。
    """
    session = _latest_session(db, user_id)
    now = _utcnow()
    if session is None:
        # 首次使用：无历史可衔接
        return {"greeting": _GREETING_FIRST, "summary": None, "isColdStart": False, "showGreeting": True}

    last = session.last_active_at
    is_cold = last is None or (now - last) > timedelta(hours=SUMMARY_IDLE_HOURS)
    if not is_cold:
        # 短离开：不生成摘要，仅骨架问候
        return {"greeting": _GREETING_SHORT, "summary": None, "isColdStart": False, "showGreeting": True}

    boundary = now - timedelta(hours=SUMMARY_IDLE_HOURS)
    summary = _summarize_previous_period(db, user_id, session.id, boundary)
    if not summary:
        return {"greeting": _GREETING_REOPEN, "summary": None, "isColdStart": True, "showGreeting": True}
    _save_topic_summary(db, user_id, session.id, summary)
    return {
        "greeting": _GREETING_AGAIN.format(summary=summary),
        "summary": summary,
        "isColdStart": True,
        "showGreeting": True,
    }


def handle_message(
    db: Session, user_id: str, content: str, explicit_intent: str | None = None,
) -> ChatReply:
    """处理一条用户消息，返回 ChatReply。

    调用方（routes/chat.py）持有请求级 db；本函数负责所有落库与留痕。
    """
    content = (content or "").strip()

    # 1. 危机前置检查（确定性，不过 LLM；事件细节绝不进画像）
    if is_crisis_signal(content):
        return _handle_crisis(db, user_id, content)

    intent = detect_intent(content, explicit_intent)
    safe_content = sanitize_text(content) or content

    session = _get_or_create_session(db, user_id)
    stack = _load_stack(session)

    profile_rows = _load_profile(db, user_id, _intent_to_profile_groups(intent))
    recent = _load_recent_messages(db, user_id, session.id)

    system = _build_system_prompt(profile_rows, stack)
    user_prompt = _build_user_prompt(recent, safe_content, intent)

    # 目标/任务意图：注入该学生的目标清单（含归档），让模型删除/更新时能引用真实标题
    if intent in ("task", "goal"):
        goals_ctx = _load_goals_context(db, user_id)
        if goals_ctx:
            system += goals_ctx

    # 知识帮助类意图：检索知识点并把真实 pointId 注入，供模型出「知识点卡」引用（#9 不许编造）
    if intent in _KNOWLEDGE_INTENTS:
        knowledge = _retrieve_knowledge_points(db, safe_content, limit=3)
        user_prompt += _format_knowledge_for_prompt(knowledge)

    # 语言风格（#20）：全量注入（不随意图组），覆盖所有转发——让 AI 按用户要求的风格说话
    system += "\n\n" + _format_style(_load_style(db, user_id))

    logger.info(
        "[CHAT] user=%s intent=%s 注入画像组=%s，注入画像条目=%s（%d 条，只记 key 不记 value）",
        user_id,
        intent,
        _intent_to_profile_groups(intent),
        sorted({e.key for e in profile_rows}),
        len(profile_rows),
    )

    provider = get_provider()
    llm_text = provider.generate(
        user_prompt,
        context={"system": system, "scene": "chat", "data_class": "state_plan"},
    )

    reply, cards, _blocked = _resolve_reply(llm_text)

    # 先问清楚再给卡：模型若在模糊学习请求（没说方向/内容）里误出了开始学习卡，
    # 直接剥掉它（它可能就是那张「基础知识点复习」卡）——只留追问文字，不默认内容。
    if _is_vague_study_request(safe_content):
        cards = [c for c in cards if not _is_start_card(c)]

    # 画像写侧（D50）：解析模型提取的画像增量并落库（事件细节不入画像由 prompt + 双重把关）
    _profile_increments = _parse_profile_increments(llm_text)
    _upsert_profile_increments(db, user_id, _profile_increments)

    # 语言风格（#20）：本轮模型识别到用户提了风格要求并写入 → **必须告知用户**已调整
    if any(it["key"] in _STYLE_KEYS for it in _profile_increments) and "风格" not in reply:
        reply = (reply.rstrip("。") + "。已按你的要求调整说话风格。")

    # 专注动作确定性兜底：LLM 没出卡 / 出的卡漏了 goal(subject) 时，
    # 用规则从原话抽「学科 + 时长」补一张，保证学科、任务、时长都能对上。
    study_card = _extract_study_card(content)
    if study_card is not None:
        valid_subjects = set(_STUDY_SUBJECT_MAP.values())
        has_valid_confirmation = any(
            c.type == "confirmation"
            and isinstance((c.payload or {}).get("goal"), dict)
            and (c.payload or {}).get("goal", {}).get("subject") in valid_subjects
            for c in cards
        )
        if not has_valid_confirmation:
            cards = [c for c in cards if c.type != "confirmation"] + [study_card]

    # 删除已归档目标确定性兜底：模型没出 delete_goal 卡、或空转问标题时，
    # 从原话识别「删除已归档」且只有唯一归档 → 补一张带真实标题的删除确认卡。
    if not any(
        c.type == "confirmation" and str((c.payload or {}).get("action")) == "delete_goal"
        for c in cards
    ):
        delete_card = _extract_delete_card(db, user_id, content)
        if delete_card is not None:
            cards = [c for c in cards if c.type != "confirmation"] + [delete_card]
            # 覆盖模型的「请告诉我标题」这类空转问句，改为驱动用户点卡确认
            reply = "已定位到你唯一一个已归档目标，确认无误后点下面卡片删除即可。"

    stack = _push_branch(stack, _intent_to_branch_type(intent), intent)
    session.context_stack_json = json.dumps(stack, ensure_ascii=False)
    session.last_active_at = _utcnow()

    _persist_raw(db, user_id, session.id, "user", safe_content)
    _persist_raw(db, user_id, session.id, "assistant", reply)
    # 仅真实调用成功才计费（Mock/失败不产生数值流水）
    if llm_text is not None:
        _record_usage(db, user_id, user_prompt, reply)

    db.commit()

    return ChatReply(
        reply=reply,
        intent=intent,
        crisis=False,
        cards=cards,
        session_id=session.id,
        context_stack=stack,
    )


def handle_ephemeral(
    db: Session, user_id: str, content: str, float_context: list[dict] | None = None,
) -> ChatReply:
    """随手问浮窗（受限 Chat 基础问答，D51 旁路）。

    关键性质：
    - **单向继承**：system 注入主对话的画像 + 上下文栈做背景，浮窗看得见主对话；
    - **不回流**：本轮的 user/assistant 不写回主对话原文、不 append 到上下文栈；
    - **不递归**：浮窗内不再派生新浮窗（前端约束），这里只做基础问答；
    - **不出卡**：剥离卡片，只回纯文本（不受引导式搜题/建目标等模式状态影响）；
    - **计费**：照常记 usage_ledger。
    """
    content = (content or "").strip()
    if is_crisis_signal(content):
        return _handle_crisis(db, user_id, content)

    intent = detect_intent(content, None)
    safe = sanitize_text(content) or content
    session = _get_or_create_session(db, user_id)
    stack = _load_stack(session)
    profile_rows = _load_profile(db, user_id, _intent_to_profile_groups(intent))
    system = _build_system_prompt(profile_rows, stack)
    system += "\n\n" + _format_style(_load_style(db, user_id))

    lines = [
        "# 随手问（受限 Chat · 基础问答）",
        "# 继承主对话背景即可；**不要出卡片、不要建议跳转/建目标/开始专注等操作，只回答这个问题**。",
    ]
    for turn in (float_context or [])[-6:]:
        who = "用户" if turn.get("role") == "user" else "助手"
        lines.append(f"{who}：{turn.get('content')}")
    lines.append(f"用户：{safe}")
    user_prompt = "\n".join(lines)

    provider = get_provider()
    llm_text = provider.generate(
        user_prompt,
        context={"system": system, "scene": "chat", "data_class": "state_plan"},
    )

    reply, _cards, _blocked = _resolve_reply(llm_text)
    # 基础问答：只回纯文本，剥离卡片；不入栈、不写回主对话原文
    if llm_text is not None:
        _record_usage(db, user_id, user_prompt, reply)
    db.commit()

    return ChatReply(
        reply=reply,
        intent=intent,
        crisis=False,
        cards=[],
        session_id=session.id,
        context_stack=stack,
    )


def _handle_crisis(db: Session, user_id: str, content: str) -> ChatReply:
    session = _get_or_create_session(db, user_id)
    session.last_active_at = _utcnow()
    _persist_raw(db, user_id, session.id, "user", content)
    _persist_raw(db, user_id, session.id, "assistant", CRISIS_RESPONSE)
    db.commit()
    logger.info("[CHAT] L3 危机转介：不过 LLM，事件细节不进画像")
    return ChatReply(
        reply=CRISIS_RESPONSE,
        intent="emotional",
        crisis=True,
        cards=[],
        session_id=session.id,
        context_stack=_load_stack(session),
    )
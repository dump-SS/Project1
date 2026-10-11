"""Chat 内核最小真链路集成测试（B 板块 M1）。

覆盖验收点：
- 一轮真实对话打通且 usage_ledger 有流水（monkeypatch 供应商）
- Mock 兜底（provider 返回 None → 温和兜底、不产生数值流水）
- 危机词触发 L3 转介且事件细节不入画像
- 上下文栈深度=3（超限沉降）
- 意图三通道：斜杠命令 / 按钮显式意图 / 模型裸判（None）
- 画像按意图选组注入（system prompt 内容断言）
- 无历史列表 / 无「新建对话」端点
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from main import app
from safety_filter import CRISIS_RESPONSE

client = TestClient(app)


class _FakeProvider:
    """返回固定文案的供应商桩，同时捕获本次 context（用于画像注入断言）。"""

    def __init__(self, reply: str = "好的，我们来看这道题，先分析定义域。") -> None:
        self.reply = reply
        self.captured: list[dict] = []

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        self.captured.append({"prompt": prompt, "context": context or {}})
        return self.reply


def _stub_provider(monkeypatch, reply: str = "好的，我们来看这道题。") -> _FakeProvider:
    import chat_engine

    fake = _FakeProvider(reply)
    monkeypatch.setattr(chat_engine, "get_provider", lambda: fake)
    return fake


def _add_profile(user_id: str, group: str, key: str, value: str) -> None:
    from database import SessionLocal
    from models.chat import UserProfile

    db = SessionLocal()
    try:
        db.add(UserProfile(
            id=f"up_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            profile_group=group,
            key=key,
            value=value,
        ))
        db.commit()
    finally:
        db.close()


def _post(user_id: str, content: str, intent: str | None = None):
    payload = {"content": content}
    if intent is not None:
        payload["intent"] = intent
    return client.post("/api/v1/chat", json=payload, headers={"X-User-ID": user_id})


# ---------- 危机转介（L3） ----------

def test_crisis_signal_referral_does_not_touch_profile_or_ledger():
    """危机词 → 固定转介文案，不过 LLM、不写画像、不产生 usage 流水。"""
    from database import SessionLocal
    from models.chat import UserProfile
    from models.governance import UsageLedger
    from sqlalchemy import select

    r = _post("chat_crisis_1", "我不想活了")
    assert r.status_code == 200
    body = r.json()
    assert body["crisis"] is True
    assert body["reply"] == CRISIS_RESPONSE
    assert body["intent"] == "emotional"

    db = SessionLocal()
    try:
        profiles = db.execute(select(UserProfile).where(UserProfile.user_id == "chat_crisis_1")).all()
        usage = db.execute(select(UsageLedger).where(UsageLedger.user_id == "chat_crisis_1")).all()
    finally:
        db.close()
    assert profiles == []       # 事件细节不进画像
    assert usage == []          # 不过 LLM，不产生数值流水


# ---------- Mock 兜底 ----------

def test_mock_provider_falls_back_without_ledger():
    """MockProvider 返回 None → 温和兜底，且不产生 usage 流水（未真实调用成功）。"""
    from database import SessionLocal
    from models.governance import UsageLedger
    from sqlalchemy import select

    r = _post("chat_mock_1", "帮我讲讲二次函数")
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]  # 非空兜底文案
    assert body["crisis"] is False

    db = SessionLocal()
    try:
        usage = db.execute(select(UsageLedger).where(UsageLedger.user_id == "chat_mock_1")).all()
    finally:
        db.close()
    assert usage == []


# ---------- 一轮真实对话 + usage_ledger ----------

def test_real_reply_writes_usage_ledger(monkeypatch):
    """供应商真实返回 → 回复透传，且 usage_ledger 落一条数值流水。"""
    from database import SessionLocal
    from models.governance import UsageLedger
    from sqlalchemy import select

    fake = _stub_provider(monkeypatch, "二次函数 y=ax²+bx+c（a≠0）的单调性取决于对称轴。")
    r = _post("chat_real_1", "二次函数单调性怎么判断")
    assert r.status_code == 200
    assert r.json()["reply"] == fake.reply

    db = SessionLocal()
    try:
        rows = db.execute(select(UsageLedger).where(UsageLedger.user_id == "chat_real_1")).scalars().all()
    finally:
        db.close()
    assert len(rows) == 1
    row = rows[0]
    assert row.feature_tier == "chat"
    assert row.tokens_in >= 1
    assert row.tokens_out >= 1


# ---------- 上下文栈深度=3 ----------

def test_context_stack_depth_capped_at_three(monkeypatch):
    """连续多次交互，栈深度恒 ≤3，超限最旧者被沉降。"""
    _stub_provider(monkeypatch)
    user = "chat_stack_1"
    max_len = 0
    for content in ["第一句", "第二句", "第三句", "第四句", "第五句"]:
        r = _post(user, content)
        assert r.status_code == 200
        stack = r.json()["contextStack"]
        max_len = max(max_len, len(stack))
        assert len(stack) <= 3
    assert max_len == 3


def test_context_stack_lifo_order(monkeypatch):
    """验收·先进后出：栈顶=最近一次，栈底=最早仍在（超限时才被沉降挤掉）。"""
    _stub_provider(monkeypatch)
    user = "chat_stack_lifo"
    _post(user, "/计划 帮我定计划")   # task   → task_draft
    _post(user, "随便聊聊")          # chat   → chat
    r = _post(user, "/出题 函数")     # practice → knowledge_help
    assert r.status_code == 200
    stack = r.json()["contextStack"]
    assert stack[-1]["branchType"] == "knowledge_help"  # 栈顶 = 最近
    assert stack[0]["branchType"] == "task_draft"       # 栈底 = 最早（深度内仍保留）


# ---------- 意图三通道 ----------

def test_intent_three_channels(monkeypatch):
    """斜杠命令 / 按钮显式意图 / 模型裸判三通道。"""
    _stub_provider(monkeypatch)

    slash = _post("chat_intent_1", "/出题 函数单调性")
    assert slash.json()["intent"] == "practice"

    button = _post("chat_intent_2", "帮我定个目标", intent="goal")
    assert button.json()["intent"] == "goal"

    bare = _post("chat_intent_3", "二次函数怎么画图")
    assert bare.json()["intent"] is None  # 裸判交模型，本层返回 None


# ---------- 画像按意图选组注入 ----------

def test_profile_injected_by_intent_group(monkeypatch):
    """goal 注入 learning+state，不含 interest；chat 注入 interest。"""
    fake = _stub_provider(monkeypatch)
    user = "chat_profile_1"
    _add_profile(user, "learning", "薄弱知识点", "函数单调性")
    _add_profile(user, "state", "情绪状态", "考试焦虑偏高")
    _add_profile(user, "interest", "兴趣", "篮球")

    _post(user, "定个数学目标", intent="goal")
    goal_system = fake.captured[-1]["context"]["system"]
    assert "薄弱知识点" in goal_system
    assert "考试焦虑偏高" in goal_system
    assert "篮球" not in goal_system      # interest 不属于 goal 的注入组

    _post(user, "随便聊聊", intent="chat")
    chat_system = fake.captured[-1]["context"]["system"]
    assert "篮球" in chat_system          # chat 意图注入 interest 组


def test_profile_injection_logs_entry_keys(monkeypatch, caplog):
    """验收·画像日志：注入时记录实际注入的画像条目 key（只记 key，不记 value）。"""
    import logging

    caplog.set_level(logging.INFO, logger="chat_engine")
    _stub_provider(monkeypatch)
    _add_profile("chat_profile_log_1", "learning", "薄弱知识点", "函数单调性")
    _add_profile("chat_profile_log_1", "state", "情绪状态", "考试焦虑偏高")
    _post("chat_profile_log_1", "定个数学目标", intent="goal")
    logs = caplog.text
    assert "注入画像条目" in logs
    assert "薄弱知识点" in logs
    assert "情绪状态" in logs


# ---------- 无历史列表 / 无新建对话（D45 红线） ----------

def test_no_history_or_new_conversation_endpoints():
    """router 只暴露 POST /chat + GET /chat/greeting（#34 问候）；无 history / new / list 端点。"""
    from routes.chat import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/chat" in paths            # 发消息
    assert any(("greeting" in (p or "")) for p in paths)  # #34 问候语（非历史列表 / 新建对话）
    # 单一对话模型红线：绝不出现 history / new / list 类端点（greeting 不在此列）
    assert not any(("history" in (p or "")) or ("new" in (p or "")) or ("list" in (p or "")) for p in paths)


# ---------- 画像写侧（D50 写侧） ----------

def test_profile_increments_written_and_filtered(monkeypatch):
    """回复含 ```profile 块 → 画像增量落库；非法 group 被过滤；块从 reply 里剥离。"""
    from database import SessionLocal
    from models.chat import UserProfile
    from sqlalchemy import select

    reply = (
        "好呀，我记住了。\n\n"
        "```profile\n"
        '{"items":['
        '{"group":"interest","key":"喜欢水果","value":"橘子"},'
        '{"group":"attribution","key":"归因","value":"总觉得自己不够努力"},'
        '{"group":"state","key":"情绪状态","value":"持续低落"},'
        '{"group":"bogus","key":"x","value":"y"}'
        "]}"
        "\n```"
    )
    _stub_provider(monkeypatch, reply)
    user = "chat_profile_write_1"
    r = _post(user, "我喜欢吃橘子")
    assert r.status_code == 200
    # fenced 块被剥离，reply 只留人话
    assert "```" not in r.json()["reply"]

    db = SessionLocal()
    try:
        rows = db.execute(select(UserProfile).where(UserProfile.user_id == user)).scalars().all()
    finally:
        db.close()
    got = {(row.profile_group, row.key, row.value) for row in rows}
    assert ("interest", "喜欢水果", "橘子") in got
    assert ("attribution", "归因", "总觉得自己不够努力") in got
    assert ("state", "情绪状态", "持续低落") in got
    assert not any(g == "bogus" for (g, _, _) in got)  # 事件/非法组被过滤


# ---------- 跨登录话题摘要（#34）：问候语 ----------

from datetime import datetime, timedelta


def _seed_session(user_id: str, last_active_age_hours: int) -> str:
    """造一个会话（last_active 距今 last_active_age_hours），返回 session_id。"""
    from database import SessionLocal
    from models.chat import ChatSession

    sid = f"cs_{user_id}"
    db = SessionLocal()
    try:
        db.add(ChatSession(
            id=sid,
            user_id=user_id,
            started_at=datetime.utcnow() - timedelta(hours=last_active_age_hours + 2),
            last_active_at=datetime.utcnow() - timedelta(hours=last_active_age_hours),
            context_stack_json=None,
        ))
        db.commit()
    finally:
        db.close()
    return sid


def _seed_raw(user_id: str, session_id: str, role: str, content: str, age_hours: int) -> None:
    from database import SessionLocal
    from models.chat import ChatRawMessage

    db = SessionLocal()
    try:
        db.add(ChatRawMessage(
            id=f"msg_{user_id}_{role}_{age_hours}",
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.utcnow() - timedelta(hours=age_hours),
            expires_at=datetime.utcnow() + timedelta(days=30),
        ))
        db.commit()
    finally:
        db.close()


def _get_greeting(user_id: str):
    return client.get("/api/v1/chat/greeting", headers={"X-User-ID": user_id})


# ---------- 目标清单注入（删除/更新目标时模型能看到真实标题） ----------

def test_goal_inventory_injected_for_goal_intent(monkeypatch):
    """goal/task 意图注入该学生的目标清单（含已归档），让模型删目标能引用真实标题。"""
    from database import SessionLocal
    from models.goal import Goal
    from sqlalchemy import select

    db = SessionLocal()
    try:
        db.add(Goal(
            id="goal_archived_1", user_id="chat_goalctx_1", type="short_term",
            subject="SX", title="务必记住的函数单调性", status="archived",
        ))
        db.add(Goal(
            id="goal_active_1", user_id="chat_goalctx_1", type="long_term",
            subject="YY", title="高中英语 3500 词", status="active",
        ))
        db.commit()
    finally:
        db.close()

    fake = _stub_provider(monkeypatch)
    r = _post("chat_goalctx_1", "帮我把那个已归档的数学目标删掉", intent="goal")
    assert r.status_code == 200
    goal_frame = fake.captured[-1]["context"]["system"]
    # 含归档目标与进行中目标，且明确标出状态
    assert "务必记住的函数单调性" in goal_frame
    assert "高中英语 3500 词" in goal_frame
    assert "已归档" in goal_frame
    assert "进行中" in goal_frame


def test_goal_inventory_not_injected_for_chat_intent(monkeypatch):
    """非目标/任务意图不注入目标清单，避免无关上下文污染。"""
    from database import SessionLocal
    from models.goal import Goal

    db = SessionLocal()
    try:
        db.add(Goal(
            id="goal_ctx_other", user_id="chat_goalctx_2", type="short_term",
            subject="SX", title="不该出现的目标", status="active",
        ))
        db.commit()
    finally:
        db.close()

    fake = _stub_provider(monkeypatch)
    _post("chat_goalctx_2", "随便聊聊", intent="chat")
    assert "不该出现的目标" not in fake.captured[-1]["context"]["system"]


# ---------- 删除已归档目标：确定性兜底卡（#17 防破甲） ----------

def test_delete_archived_goal_deterministic_card(monkeypatch):
    """模型空转问标题时，后端按规则识别「删除已归档」且唯一归档 → 补真实标题的删除确认卡。"""
    from database import SessionLocal
    from models.goal import Goal

    db = SessionLocal()
    try:
        db.add(Goal(
            id="goal_del_archived", user_id="chat_delarc_1", type="short_term",
            subject="SX", title="数学错题订正", status="archived",
        ))
        db.commit()
    finally:
        db.close()

    # 模型给一个「请告诉我标题」的空转回复（不带卡）
    _stub_provider(monkeypatch, "你需要删除的已归档目标具体标题是什么呢？")
    user = "chat_delarc_1"
    payload = {"content": "删除已归档任务"}
    r = client.post("/api/v1/chat", json=payload, headers={"X-User-ID": user})
    assert r.status_code == 200
    body = r.json()
    delete_cards = [c for c in body["cards"] if c.get("payload", {}).get("action") == "delete_goal"]
    assert len(delete_cards) == 1, "应有确定性删除确认卡"
    goal = delete_cards[0]["payload"]["goal"]
    assert goal["title"] == "数学错题订正"
    assert goal["subject"] == "SX"
    # 空转问句被覆盖，不再让用户补标题
    assert "点下面卡片删除" in body["reply"]


def test_no_delete_card_when_multiple_archived(monkeypatch):
    """有多个已归档目标时不强行出卡（避免猜错目标，交回模型/让用户明确）。"""
    from database import SessionLocal
    from models.goal import Goal

    db = SessionLocal()
    try:
        db.add(Goal(id="g_da1", user_id="chat_delarc_2", type="short_term", subject="SX", title="数学A", status="archived"))
        db.add(Goal(id="g_da2", user_id="chat_delarc_2", type="short_term", subject="DL", title="地理B", status="archived"))
        db.commit()
    finally:
        db.close()

    fake = _stub_provider(monkeypatch, "你要删的是哪一个？")
    r = client.post("/api/v1/chat", json={"content": "删除已归档任务"}, headers={"X-User-ID": "chat_delarc_2"})
    assert r.status_code == 200
    del_cards = [c for c in r.json()["cards"] if c.get("payload", {}).get("action") == "delete_goal"]
    assert del_cards == []


def test_no_delete_card_without_archived_kw(monkeypatch):
    """用户没说「归档」，即使只有一个归档目标也不强行删（绝不猜目标）。"""
    from database import SessionLocal
    from models.goal import Goal

    db = SessionLocal()
    try:
        db.add(Goal(id="g_da3", user_id="chat_delarc_3", type="short_term", subject="SX", title="数学错题订正", status="archived"))
        db.commit()
    finally:
        db.close()

    fake = _stub_provider(monkeypatch, "你要删哪个进行中的目标？")
    r = client.post("/api/v1/chat", json={"content": "帮我删个目标"}, headers={"X-User-ID": "chat_delarc_3"})
    assert r.status_code == 200
    del_cards = [c for c in r.json()["cards"] if c.get("payload", {}).get("action") == "delete_goal"]
    assert del_cards == []

# ---------- 先问清楚再给开始卡（#17 / D53 别替用户做决定） ----------

def test_vague_study_request_no_start_card():
    """「想学地理」未指定方向/内容 → 不出开始学习卡、不默认内容，交回模型追问。"""
    import chat_engine
    assert chat_engine._extract_study_card("我今天想学一会儿地理") is None
    assert chat_engine._extract_study_card("我想学数学") is None


def test_focus_with_duration_still_gives_card():
    """明确时长 + 专注动作（如「25分钟专注数学」）→ 仍出开始卡（通用专注内容可接受）。"""
    import chat_engine
    assert chat_engine._extract_study_card("数学，25分钟专注") is not None


def test_specific_direction_gives_card():
    """有具体方向（如背单词/刷题）→ 出开始卡。"""
    import chat_engine
    assert chat_engine._extract_study_card("地理背单词") is not None
    assert chat_engine._extract_study_card("数学刷题") is not None


def test_vague_request_strips_model_start_card(monkeypatch):
    """模型在模糊学习请求里误出开始卡 → 后端剥掉，只留追问。"""
    model_out = (
        "好的，你想复习地理哪个方向呢？\n\n"
        "```json\n"
        '{"type":"confirmation","title":"准备开始地理学习",'
        '"payload":{"action":"start_study","task":"地理 · 基础知识点复习",'
        '"goal":{"subject":"DL","title":"今日地理学习"},'
        '"plan":{"availableMinutes":25}},"display":{"summary":"为你安排：地理 · 基础知识点复习（25 分钟）"}}'
        "\n```"
    )
    _stub_provider(monkeypatch, model_out)
    r = client.post("/api/v1/chat", json={"content": "我今天想学一会儿地理"}, headers={"X-User-ID": "chat_vague_2"})
    assert r.status_code == 200
    body = r.json()
    assert body["cards"] == [] or all(
        not (c.get("type") == "confirmation" and (c.get("payload", {}).get("action") == "start_study"))
        for c in body["cards"]
    ), "模糊学习请求的模型开始卡应被剥掉"


def _post_ephemeral(user_id: str, content: str, float_context: list[dict] | None = None):
    payload = {"content": content, "ephemeral": True}
    if float_context:
        payload["floatContext"] = float_context
    return client.post("/api/v1/chat", json=payload, headers={"X-User-ID": user_id})


def test_ephemeral_base_qa_no_cards_no_stack_no_callback(monkeypatch):
    """随手问浮窗：回纯文本、不出卡、不入栈、不写回主对话原文；计费正常。"""
    from database import SessionLocal
    from models.chat import ChatRawMessage
    from models.governance import UsageLedger
    from sqlalchemy import func, select

    fake = _stub_provider(monkeypatch, "「函数」就是输入到输出的一个映射关系。")
    user = "chat_float_1"
    r = _post_ephemeral(user, "函数是什么意思")
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == fake.reply
    assert body["cards"] == []            # 基础问答不出卡
    assert body["contextStack"] == []     # 不入栈

    db = SessionLocal()
    try:
        raw_cnt = db.execute(
            select(func.count()).select_from(ChatRawMessage).where(ChatRawMessage.user_id == user)
        ).scalar_one()
        usage_rows = db.execute(select(UsageLedger).where(UsageLedger.user_id == user)).scalars().all()
    finally:
        db.close()
    assert raw_cnt == 0                   # 不回流主对话原文
    assert len(usage_rows) == 1           # 照常计费


def test_ephemeral_inherits_float_context_multi_turn(monkeypatch):
    """浮窗内多轮追问：前端把前几轮经 floatContext 传入，prompt 里能读到。"""
    fake = _stub_provider(monkeypatch, "单糖是葡萄糖、果糖、半乳糖.")
    r = _post_ephemeral(
        "chat_float_2", "那单糖呢", [{"role": "user", "content": "糖分哪几类"}, {"role": "assistant", "content": "多糖、单糖…"}]
    )
    assert r.status_code == 200
    assert r.json()["reply"] == fake.reply
    joined = "\n".join(c["prompt"] for c in fake.captured)
    assert "糖分哪几类" in joined        # 前一轮被带上
    assert "那单糖呢" in joined


def test_greeting_cold_start_generates_and_stores_summary(monkeypatch):
    """冷启动（离开>12h，有保留原文）→ 生成摘要、落库 topic_summaries、问候语含摘要。"""
    from database import SessionLocal
    from models.chat import TopicSummary
    from sqlalchemy import select

    summary_out = "· 上次在讲函数单调性\n· 卡在复合函数求导"
    fake = _stub_provider(monkeypatch, summary_out)

    user = "chat_summary_cold"
    sid = _seed_session(user, last_active_age_hours=48)          # 离开 2 天 → 冷启动
    _seed_raw(user, sid, "user", "帮我讲讲函数单调性", age_hours=47)
    _seed_raw(user, sid, "assistant", "好的，我们看对称轴。", age_hours=45)

    r = _get_greeting(user)
    assert r.status_code == 200
    body = r.json()
    assert body["isColdStart"] is True
    assert body["summary"] == summary_out
    assert "函数单调性" in body["greeting"]

    db = SessionLocal()
    try:
        rows = db.execute(select(TopicSummary).where(TopicSummary.user_id == user)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].summary == summary_out
    assert rows[0].session_id == sid


def test_greeting_short_leave_skips_generation(monkeypatch):
    """短离开（≤12h）→ 不生成摘要、不落库、不调 LLM。"""
    from database import SessionLocal
    from models.chat import TopicSummary
    from sqlalchemy import select

    fake = _stub_provider(monkeypatch, "· 上次在学函数单调性")

    user = "chat_summary_short"
    _seed_session(user, last_active_age_hours=1)                 # 1 小时前活跃 → 短离开

    r = _get_greeting(user)
    assert r.status_code == 200
    body = r.json()
    assert body["isColdStart"] is False
    assert body["summary"] is None
    assert "函数单调性" not in body["greeting"]

    assert fake.captured == []                                   # 没调 LLM

    db = SessionLocal()
    try:
        rows = db.execute(select(TopicSummary).where(TopicSummary.user_id == user)).scalars().all()
    finally:
        db.close()
    assert rows == []                                            # 没落库


# ---------- 语言风格（#20：画像字段，全量注入，变更必告知） ----------

def test_style_injected_for_any_intent(monkeypatch):
    """语言风格全量注入：任意意图（含 chat）system 里都有风格指令与具体风格值。"""
    _add_profile("chat_style_1", "interest", "style", "简洁，别啰嗦，直接给结论")
    fake = _stub_provider(monkeypatch)
    r = _post("chat_style_1", "随便聊聊", intent="chat")
    assert r.status_code == 200
    system = fake.captured[-1]["context"]["system"]
    assert "语言风格" in system
    assert "简洁" in system            # 风格值被注入


def test_style_write_and_notify(monkeypatch):
    """对话提风格要求 → 模型写 profile 块 → 落库 + 回复明确告知已调整。"""
    from database import SessionLocal
    from models.chat import UserProfile
    from sqlalchemy import select

    model_out = (
        "好的，我说短一点。\n\n"
        "```profile\n"
        '{"items":[{"group":"interest","key":"style","value":"简洁"}]}'
        "\n```"
    )
    _stub_provider(monkeypatch, model_out)
    user = "chat_style_2"
    r = _post(user, "你说话别这么啰嗦")
    assert r.status_code == 200
    body = r.json()
    assert "风格" in body["reply"]      # 已告知用户完成调整
    assert "已按你的要求调整说话风格" in body["reply"]

    db = SessionLocal()
    try:
        rows = db.execute(select(UserProfile).where(UserProfile.user_id == user, UserProfile.key.in_(("style", "语言风格")))).scalars().all()
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].profile_group == "interest"
    assert rows[0].value == "简洁"
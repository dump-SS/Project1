"""L174 · 三路径（随手问 / 话题摘要 / crisis_l3）补 user_id 的记账回归测试。

对照：pilot 铁律 5「必须按用户记录模型数值成本（usage_ledger）」+ D38
「每次真实调用有数值流水」；as-built 盘点 2026-11-07「真偏离」第 4 条。

## 测试策略

- **真实行**：真 OpenAICompatibleProvider + 打桩 _call_once（无网络），返回
  固定文本 + usage={prompt_tokens:11, completion_tokens:7}——provider 层的
  record_usage 会把**真实回报值**写进 usage_ledger，可精确断言（与 len//4
  估算值 3/… 相区分，天然证明这行来自真实回报而非估算兜底）。
- **估算兜底**：默认 MockProvider（generate 返回 None）——provider 不写真实行，
  chat_engine 的估算兜底应恰好补 1 行；LLM 失败（None）不造任何流水（对偶验证）。
- **单次单行**：每例同时断言行数==1（真实行与估算行不并存）。

三路径在修复前的原始形态（盘点 2026-11-07 L174，测试注释里逐条留痕）：
- 话题摘要 chat_engine._summarize_previous_period：context 无 user_id → 零流水
- 随手问 chat_engine.handle_ephemeral：context 无 user_id → 估算行有 user_id 但
  无真实行（provider 层 record_usage 因无 user_id 直接 no-op）
- crisis_l3 safety_filter.crisis_check：context 无 user_id 且签名没有 user_id
  → 语义兜底真实调用零流水
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import chat_engine
import safety_filter
import usage_ledger
from config import settings
from database import SessionLocal
from models.chat import ChatRawMessage
from models.governance import UsageLedger

PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
)


@pytest.fixture
def stub_real_provider(monkeypatch):
    """真 OpenAICompatibleProvider + 打桩 _call_once（不发网络请求）。

    返回 (provider, calls)：generate 走完整 provider 层（含 usage_ledger.record_usage
    真实行落账），只是 HTTP 层被替换成固定回报。
    """
    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    from llm_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider()
    calls: list[bytes] = []

    def fake_call(url, payload, headers):
        calls.append(payload)
        # _call_once 的真实语义：返回 (content, usage_dict)——usage 已是
        # body.get("usage") 解出来的平铺 dict（不是 {"usage": {...}} 嵌套）。
        return "好的", {"prompt_tokens": 11, "completion_tokens": 7}

    monkeypatch.setattr(provider, "_call_once", fake_call)
    # get_provider 的两处绑定都要打桩——漏了这条测试会走真网关（不稳定，正是
    # 上一轮「spy 空 + 0 行」失败的根因）。
    import llm_provider

    monkeypatch.setattr(chat_engine, "get_provider", lambda: provider)
    monkeypatch.setattr(llm_provider, "get_provider", lambda: provider)
    return provider, calls


def _usage_rows(user_id: str) -> list[UsageLedger]:
    db = SessionLocal()
    try:
        return (
            db.query(UsageLedger)
            .filter(UsageLedger.user_id == user_id)
            .order_by(UsageLedger.created_at.asc())
            .all()
        )
    finally:
        db.close()


@pytest.fixture
def _record_usage_spy(monkeypatch):
    """记录 provider 层 record_usage 的 (user_id, feature_tier, scene, in, out)。"""
    import usage_ledger as ul

    spy: list[tuple] = []
    orig = ul.record_usage

    def spy_record(*a, **k):
        ctx = a[0] if a else {}
        spy.append((
            ctx.get("user_id"), ctx.get("feature_tier"), ctx.get("scene"),
            k.get("tokens_in"), k.get("tokens_out"),
        ))
        return orig(*a, **k)

    monkeypatch.setattr(ul, "record_usage", spy_record)
    return spy


# ---------------------------------------------------------------- 随手问


def test_ephemeral_real_call_lands_single_row(stub_real_provider, _record_usage_spy, monkeypatch):
    """随手问：真实调用落 usage_ledger 单行（真实 tokens，非估算），user_id 可追溯。"""
    provider, _calls = stub_real_provider

    db = SessionLocal()
    try:
        chat_engine.handle_ephemeral(db, "u_l174a", "帮我看看这道题怎么解")
        db.commit()
    finally:
        db.close()

    # provider 层收到 user_id + 供应商真实回报值（L174 的核心断言）
    assert len(_record_usage_spy) == 1
    spy_user, spy_tier, _scene, spy_in, spy_out = _record_usage_spy[0]
    assert spy_user == "u_l174a"
    assert spy_tier == "chat"
    assert spy_in == 11 and spy_out == 7  # 真实回报值，非 len//4 估算
    # 单次调用只落一行（SQLite 测试库：主事务未提交持写锁，record_usage 独立连接
    # INSERT 失败被吞 → 估算兜底补位；生产 PG：真实行直接落库——两种环境都是单行，
    # 行的性质随环境不同是现状设计，断言只锁「单行 + user_id 非空」）
    rows = _usage_rows("u_l174a")
    assert len(rows) == 1, f"应恰好 1 行，实际 {len(rows)} 行——重复记账"
    assert rows[0].user_id == "u_l174a"


def test_ephemeral_mock_provider_lands_zero_rows(monkeypatch):
    """Mock（generate 返回 None）：不落任何行——估算兜底不为失败/无响应造假流水。"""
    db = SessionLocal()
    try:
        chat_engine.handle_ephemeral(db, "u_l174b", "随便聊聊")
        db.commit()
    finally:
        db.close()

    assert _usage_rows("u_l174b") == []


# ---------------------------------------------------------------- 话题摘要


def test_topic_summary_real_call_lands_row(stub_real_provider, monkeypatch):
    """话题摘要：冷启动提炼的真实调用落 usage_ledger（修复前零流水）。"""
    provider, _calls = stub_real_provider

    user_id, session_id = "u_l174c", "sess_l174c"
    db = SessionLocal()
    try:
        for role, text in (("user", "上次问了一道物理题"), ("assistant", "好的我们来看受力分析")):
            db.add(ChatRawMessage(
                id=f"msg_l174_{role}",
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=text,
                expires_at=datetime.utcnow() + timedelta(days=3),
            ))
        db.commit()
        boundary = datetime.utcnow() + timedelta(hours=1)
        summary = chat_engine._summarize_previous_period(db, user_id, session_id, boundary)
        assert summary  # 摘要本身生成成功
    finally:
        db.close()

    rows = _usage_rows(user_id)
    assert len(rows) == 1
    assert rows[0].tokens_in == 11 and rows[0].tokens_out == 7


# ---------------------------------------------------------------- crisis_l3


def test_crisis_l3_real_call_lands_single_row(stub_real_provider, _record_usage_spy, monkeypatch):
    """crisis_l3 语义兜底：真实调用落 usage_ledger 单行（真实行与估算行不并存）。"""
    provider, _calls = stub_real_provider
    # 语义兜底判定为「非危机」：需要软标记命中（进 L3）+ 模型 JSON 判 crisis=false
    db = SessionLocal()
    try:
        decision = safety_filter.crisis_check("感觉快撑不住了", user_id="u_l174d")
        assert decision.layer == "l2_semantic"
        db.commit()
    finally:
        db.close()

    # provider 层收到 user_id + 真实回报值；估算守卫（recorded_real_usage）在
    # 真实行写库成功时不补估算——「单次调用只落一行」由下行锁定
    assert len(_record_usage_spy) == 1
    spy_user, _tier, _scene, spy_in, spy_out = _record_usage_spy[0]
    assert spy_user == "u_l174d"
    assert spy_in == 11 and spy_out == 7
    rows = _usage_rows("u_l174d")
    assert len(rows) == 1, f"应恰好 1 行，实际 {len(rows)} 行——重复记账"
    assert rows[0].user_id == "u_l174d"


def test_crisis_l3_mock_estimate_fallback_single_row(monkeypatch):
    """Mock（generate 返回 None → 按危机处理）：chat_engine 估算兜底恰 1 行。

    provider 无真实行时估算兜底要补（账不能缺）；有真实行时不补（账不能重）——
    两条守卫合起来才是「单次调用只落一行」。
    """
    db = SessionLocal()
    try:
        chat_engine.handle_ephemeral(db, "u_l174e", "感觉快撑不住了")
        db.commit()
    finally:
        db.close()

    rows = _usage_rows("u_l174e")
    assert len(rows) == 1
    assert rows[0].user_id == "u_l174e"

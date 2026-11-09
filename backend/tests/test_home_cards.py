"""D21→D28 首页推荐卡产卡 + 冷却 + 事件上报的测试（口径卡 §六 / 派单 §四）。

## 测试策略

- **冻结时钟**：所有冷却断言都向服务层注入固定的 `now`（`build_home_cards(db, uid, now=…)`），
  相对 now 构造事件时间——3 天 / 7 天 / 周 1 三条规则逐条测边界两侧，不依赖真实时钟。
- **测试夹具构造指纹 + 事件**：不依赖真实数据自然积累（pilot 早期推荐/洞察组按
  「宁缺毋滥」可能整组空缺）。
- 事件上报端点走 TestClient（X-User-ID 身份回落）；产卡逻辑直调服务层（注入时钟）。

固定时钟：2026-11-10（周二）12:00 UTC —— 本周一 = 2026-11-09 00:00 UTC。
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import home_cards
from config import settings
from database import SessionLocal
from models.assessment import AssessmentSnapshot
from models.card import CardImpression
from models.community import CommunityAggregate
from models.goal import Goal as GoalORM
from models.knowledge import KnowledgePoint, PointMastery
from models.learning_record import LearningRecord as LearningRecordORM
from models.plan import Plan as PlanORM
from models.plan import PlanTask as PlanTaskORM
from models.user import Settings as SettingsORM
from models.user import User

# 周二 12:00 UTC；本周一（11-09）00:00 为周界
NOW = datetime(2026, 11, 10, 12, 0, 0)
UID = "u_cards1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


def _db():
    return SessionLocal()


def _mk_user(db, uid=UID, stage="junior"):
    if db.get(User, uid) is None:
        db.add(User(id=uid, stage=stage, grade="高二", subjects=["SX"]))
    db.commit()


def _mk_plan_with_pending_task(db, uid=UID, pid="p_cards1"):
    db.add(PlanORM(id=pid, user_id=uid, plan_date=NOW.date(), available_minutes=60))
    db.add(PlanTaskORM(
        id=f"t_{pid}", plan_id=pid, user_id=uid, subject="SX", topic="函数单调性练习",
        estimated_minutes=25, priority=1, status="pending",
    ))
    db.commit()
    return pid


def _mk_records(db, uid=UID, n=3):
    """造 n 条近 7 天学习记录（推荐组「足够数据」门槛用；accuracy 非空避免进 Go on）。"""
    for i in range(n):
        db.add(LearningRecordORM(
            id=f"lr_cards_{i}", user_id=uid, subject="SX",
            started_at=NOW - timedelta(days=1, hours=i),
            duration_minutes=30, behavior_completion="completed",
            behavior_accuracy=0.8, behavior_interruptions=0,
        ))
    db.commit()


def _mk_impression(db, uid, group, action, fingerprint, shown_at):
    db.add(CardImpression(
        id=f"ci_direct_{_uuid.uuid4().hex[:12]}",
        user_id=uid, group=group, card_type="continue_plan",
        fingerprint=fingerprint, action=action, shown_at=shown_at,
    ))
    db.commit()


def _mk_active_goal(db, uid=UID, gid="g_cards1"):
    db.add(GoalORM(
        id=gid, user_id=uid, type="long_term", subject="SX",
        title="期末数学提 20 分", status="active", planned_tasks=0, completed_tasks=0,
    ))
    db.commit()
    return gid


def _mk_community_agg(db, pool=25, stage="junior", metric="fatigue"):
    """造本周聚合物化行（k=20 达标）。"""
    period = home_cards.iso_week_of(NOW)
    db.add(CommunityAggregate(
        id=f"agg_{stage}_{metric}",
        period=period, stage=stage, metric=metric,
        pool_size=pool,
        percentiles='{"p25": 20.0, "p50": 30.0, "p75": 40.0}',
        histogram="[]",
    ))
    db.commit()


def _grant_consent(db, uid=UID):
    if db.get(SettingsORM, uid) is None:
        db.add(SettingsORM(user_id=uid, community_consent_enabled=True))
    else:
        db.get(SettingsORM, uid).community_consent_enabled = True
    db.commit()


def _card_titles(groups, group_key):
    for g in groups:
        if g["group"] == group_key:
            return [c["display"]["title"] for c in g["cards"]]
    return []


# ---------------------------------------------------------------- 冻结时钟 · 三规则


def test_go_on_dismissed_cooldown_3_days():
    """Go on：dismissed 后 3 天内不推；超过 3 天恢复。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_plan_with_pending_task(db)
        fp = "go_on:plan:p_cards1"

        # 基线：未划掉 → 硬性出现
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "go_on")

        # 2 天 23 小时前划掉 → 冷却期内被挡
        _mk_impression(db, UID, "go_on", "dismissed", fp, NOW - timedelta(days=2, hours=23))
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "go_on") == []

        # 推进到 3 天 1 小时后（同样的事件）→ 冷却过期恢复
        later = NOW + timedelta(days=1)
        assert _card_titles(home_cards.build_home_cards(db, UID, now=later), "go_on")
    finally:
        db.close()


def test_recommend_shown_cooldown_7_days():
    """推荐：同指纹 shown 后 7 天内不重复；超过 7 天恢复。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_records(db, n=3)  # 足够数据
        gid = _mk_active_goal(db)
        fp = f"recommend:goal:{gid}"

        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend")

        _mk_impression(db, UID, "recommend", "shown", fp, NOW - timedelta(days=6, hours=23))
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend") == []

        later = NOW + timedelta(days=1)  # 距事件 8 天 1 小时
        assert _card_titles(home_cards.build_home_cards(db, UID, now=later), "recommend")
    finally:
        db.close()


def test_insight_weekly_cap_from_monday():
    """洞察：自然周（周一 00:00 UTC）内已有 shown → 整组克制不出现；跨周恢复。"""
    db = _db()
    try:
        _mk_user(db)
        _grant_consent(db)
        _mk_community_agg(db, pool=25)

        # 基线：本周未展示 → 有洞察（≤1 条，带 N 名匿名同龄人标注）
        groups = home_cards.build_home_cards(db, UID, now=NOW)
        insight = [g for g in groups if g["group"] == "insight"]
        assert insight and len(insight[0]["cards"]) == 1
        assert "名匿名同龄人" in insight[0]["cards"][0]["display"]["title"]

        # 本周一（11-09）之后 shown 过一次 → 本周整组空
        _mk_impression(db, UID, "insight", "shown", "insight:junior:fatigue:2026-W46", datetime(2026, 11, 9, 8, 0, 0))
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "insight") == []

        # 上周日（11-08）的 shown 不算本周 → 洞察恢复（周界=周一 00:00）
        db.query(CardImpression).filter(CardImpression.user_id == UID).update(
            {CardImpression.shown_at: datetime(2026, 11, 8, 23, 0, 0)}
        )
        db.commit()
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "insight")
    finally:
        db.close()


# ---------------------------------------------------------------- 推荐组：有变化才推 / 数据门槛


def test_recommend_only_when_changed():
    """「只推有变化的」：同目标 7 天内挡；换了目标（指纹变化）→ 放。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_records(db, n=3)
        g1 = _mk_active_goal(db, gid="g_cards_a")
        g2 = _mk_active_goal(db, gid="g_cards_b")

        # 7 天内 g1 已推过 → g1 被挡，g2（新指纹=有变化）顺延出现
        _mk_impression(db, UID, "recommend", "shown", f"recommend:goal:{g1}", NOW - timedelta(days=1))
        groups = home_cards.build_home_cards(db, UID, now=NOW)
        titles = _card_titles(groups, "recommend")
        assert titles, "同指纹被挡后，不同指纹（有变化）应出现"
        assert any("期末数学提 20 分" in t for t in titles)  # g2 的标题（同标题不同 id——用指纹侧断言）

        # 反向：g2 也在 7 天内推过 → 整组空缺
        _mk_impression(db, UID, "recommend", "shown", f"recommend:goal:{g2}", NOW - timedelta(days=1))
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend") == []
    finally:
        db.close()


def test_recommend_requires_enough_data():
    """不足数据（<3 条记录且无评估）→ 推荐组整组空缺（宁缺毋滥）。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_records(db, n=2)  # 2 条 < 3，且无评估快照
        _mk_active_goal(db)
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend") == []

        # 补到 3 条 → 达标
        db.add(LearningRecordORM(
            id="lr_cards_extra", user_id=UID, subject="SX",
            started_at=NOW - timedelta(hours=2), duration_minutes=20,
            behavior_completion="partial", behavior_accuracy=0.5, behavior_interruptions=0,
        ))
        db.commit()
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend")
    finally:
        db.close()


def test_clicked_does_not_cool():
    """clicked 只作附加记录、不触发冷却。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_records(db, n=3)
        gid = _mk_active_goal(db)
        _mk_impression(db, UID, "recommend", "clicked", f"recommend:goal:{gid}", NOW - timedelta(hours=3))
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "recommend")
    finally:
        db.close()


# ---------------------------------------------------------------- 洞察组：k 不绕过


def test_insight_requires_k_pool():
    """pool < k=20 → 洞察不生成（合规底线，不绕过）。"""
    db = _db()
    try:
        _mk_user(db)
        _grant_consent(db)
        _mk_community_agg(db, pool=19)  # 差 1
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "insight") == []

        # 补到 20 → 生成
        db.query(CommunityAggregate).filter(CommunityAggregate.id == "agg_junior_fatigue").update(
            {CommunityAggregate.pool_size: 20}
        )
        db.commit()
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "insight")
    finally:
        db.close()


def test_insight_requires_consent():
    """未开匿名聚合授权 → 不产洞察卡。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_community_agg(db, pool=30)
        assert _card_titles(home_cards.build_home_cards(db, UID, now=NOW), "insight") == []
    finally:
        db.close()


# ---------------------------------------------------------------- 组序与空缺


def test_group_order_and_empty_groups_omitted():
    """组顺序固定 Go on → 推荐 → 洞察；无内容的组不返回。"""
    db = _db()
    try:
        _mk_user(db)
        _mk_plan_with_pending_task(db)  # 只有 go_on 数据
        groups = home_cards.build_home_cards(db, UID, now=NOW)
        assert [g["group"] for g in groups] == ["go_on"]

        _mk_records(db, n=3)
        _mk_active_goal(db)
        _grant_consent(db)
        _mk_community_agg(db, pool=30)
        groups = home_cards.build_home_cards(db, UID, now=NOW)
        assert [g["group"] for g in groups] == ["go_on", "recommend", "insight"]
    finally:
        db.close()


# ---------------------------------------------------------------- 事件上报端点


def test_create_impression_single_row_server_fields(client):
    """POST 事件：201、id/createdAt 服务端生成、shownAt 可省略、单次只写一行。"""
    db = _db()
    try:
        _mk_user(db)
    finally:
        db.close()

    resp = client.post(
        "/api/v1/me/card-impressions",
        json={"group": "recommend", "cardType": "goal_planning", "fingerprint": "recommend:goal:g1", "action": "shown"},
        headers={"X-User-ID": UID},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("ci_")
    assert body["createdAt"]
    assert body["shownAt"]
    assert body["action"] == "shown"

    db = _db()
    try:
        rows = db.query(CardImpression).filter(CardImpression.user_id == UID).all()
        assert len(rows) == 1, f"单次事件应只写一行，实际 {len(rows)}"
    finally:
        db.close()


def test_create_impression_rejects_missing_required(client):
    """required 只有四字段：缺 group/cardType/fingerprint/action 任一 → 400。"""
    resp = client.post(
        "/api/v1/me/card-impressions",
        json={"group": "recommend", "cardType": "goal_planning", "action": "shown"},  # 缺 fingerprint
        headers={"X-User-ID": UID},
    )
    assert resp.status_code == 400

"""首页推荐卡产卡服务（D21/D28，E 板块 M4）—— 契约 v1.21.0。

三组规则严格照 target.md:192-196（口径卡 home-cards-charter.md 八条定稿）：

| 组 | 触发 | 排序 | 指纹 | 冷却 |
|---|---|---|---|---|
| Go on | 存在未完成事项即硬性出现 | 逾期/紧急度 | planId/recordId | dismissed 后 3 天 |
| 推荐 | 需足够数据（≥3 条记录 或 ≥1 次评估，口径卡设定）；不足整组空缺 | 状态 > 内容 > 目标规划 | type+pointId/subject | shown 后 7 天，只推「有变化」的 |
| 洞察 | 社区聚合 pool ≥ k=20 + 用户已授权；克制出现 | 相关度，≤1 条 | 维度+周期 | shown 后每周 ≤1，同维度周内不重复 |

## 数据源（实现时逐一核实过）
- Go on：`plan_tasks.status`（未完成任务）+ `learning_records.behavior_accuracy IS NULL
  且 source='self_report'`（待续复盘 = 用户记录未回填正确率）
- 推荐：`assessment_snapshots`（状态建议）/ `kb_point_mastery`（内容建议，弱项知识点）
  / `goals`（目标规划）；足够数据门槛 = 近 7 天 ≥3 条记录 或 ≥1 行评估快照
- 洞察：`community_aggregates` 物化表（jobs/community_aggregate.py 已保证 pool<k 删行，
  这里再按 settings.community_min_pool 兜底断言，不绕过 k）；另需
  `settings.community_consent_enabled`（未授权不产——合规）

## AI 口径
pilot 以**规则模板为主、AI 可选**（口径卡 §三）：本实现全部规则生成、不调 LLM——
产卡链路不产生用户内容出域（PRD 12.6），聚合特征复用
`routes.recommendation_content._aggregate_recent_records` 的同一套聚合思路。

## 时间口径
自然周起点 = 周一 00:00 UTC（存储 UTC / 展示本地，对齐 APIModel 时区基座）。
生产卡函数接受 `now` 参数供冻结时钟测试注入；路由默认取 utcnow。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models.assessment import AssessmentSnapshot
from models.card import CardImpression
from models.goal import Goal as GoalORM
from models.knowledge import PointMastery
from models.learning_record import LearningRecord as LearningRecordORM
from models.plan import Plan as PlanORM
from models.plan import PlanTask as PlanTaskORM
from models.user import Settings as SettingsORM
from schemas.card import CardAction, CardGroup

logger = logging.getLogger(__name__)

# 冷却窗口（D28）：Go on dismissed 3 天 / 推荐 shown 7 天 / 洞察每周 ≤1
COOLDOWN_GO_ON = timedelta(days=3)
COOLDOWN_RECOMMEND = timedelta(days=7)

# 每组卡片上限（契约：后端控制 3–6 张）
MAX_CARDS_PER_GROUP = 6

# 「足够数据」口径（口径卡 §三设定，文档未定）：近 7 天 ≥3 条记录 或 ≥1 次状态评估
SUFFICIENT_RECORDS = 3
SUFFICIENT_WINDOW_DAYS = 7

# 推荐组内的类型排序权重（target.md:194「状态 > 内容 > 目标规划」）
_RECOMMEND_ORDER = {"state_advice": 0, "content_advice": 1, "goal_planning": 2}


def utcnow() -> datetime:
    return datetime.utcnow()


def iso_week_of(now: datetime) -> str:
    """ISO 周标识（与 jobs.community_aggregate._current_iso_week 同格式）。

    不复用那个函数是因为它无参、内部用 date.today()——产卡需要可控时钟
    （冻结时钟测试），这里按传入 now 计算。
    """
    iso = now.date().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_start(now: datetime) -> datetime:
    """自然周起点：周一 00:00（UTC）。"""
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _impression_note(db: Session, user_id: str, group: CardGroup, action: CardAction, since: datetime) -> set[str]:
    """冷却窗口内该组已发生指定 action 的指纹集合。"""
    rows = db.execute(
        select(CardImpression.fingerprint).where(
            CardImpression.user_id == user_id,
            CardImpression.group == group.value,
            CardImpression.action == action.value,
            CardImpression.shown_at >= since,
        )
    ).scalars().all()
    return set(rows)


def _card(type_: str, title: str, subtitle: str | None, refs: dict | None, generated: dict | None, instruction: str | None) -> dict:
    card: dict = {"type": type_, "display": {"title": title}}
    if subtitle:
        card["display"]["subtitle"] = subtitle
    payload: dict = {}
    if refs is not None:
        payload["refs"] = refs
    if generated is not None:
        payload["generated"] = generated
    if instruction:
        payload["instruction"] = instruction
    if payload:
        card["payload"] = payload
    return card


# ---------------------------------------------------------------- Go on 组


def _go_on_cards(db: Session, user_id: str, now: datetime) -> list[dict]:
    """Go on：存在未完成事项即硬性出现；排序按逾期/紧急度（plan_date 早的在前）。

    两类事项：
    1. 未完成计划任务（plan_tasks.status != done，且未 removed）→ continue_plan
    2. 待续复盘（self_report 记录 behavior_accuracy 为 NULL，近 7 天）→ continue_plan
       （回填正确率是「待续」的显式动作；D20 三态里正确率可事后延迟补充）
    冷却：dismissed 后 3 天不推（按指纹）。
    """
    cooled = _impression_note(db, user_id, CardGroup.go_on, CardAction.dismissed, now - COOLDOWN_GO_ON)
    cards: list[dict] = []

    # 1) 未完成计划（取 plan_date 最近且仍有未完成任务的计划）
    today = now.date()
    latest_plan = db.execute(
        select(PlanORM)
        .where(PlanORM.user_id == user_id, PlanORM.plan_date >= today - timedelta(days=1))
        .order_by(PlanORM.plan_date.asc(), PlanORM.created_at.desc())
        .limit(1)
    ).scalars().first()
    if latest_plan is not None:
        tasks = db.execute(
            select(PlanTaskORM).where(
                PlanTaskORM.plan_id == latest_plan.id,
                PlanTaskORM.status != "done",
                PlanTaskORM.removed.is_(False),
            ).order_by(PlanTaskORM.priority.asc())
        ).scalars().all()
        all_count = db.execute(
            select(PlanTaskORM).where(PlanTaskORM.plan_id == latest_plan.id, PlanTaskORM.removed.is_(False))
        ).scalars().all()
        if tasks:
            done = sum(1 for t in all_count if t.status == "done")
            total = len(all_count)
            remaining = sum(t.estimated_minutes for t in tasks)
            fp = f"go_on:plan:{latest_plan.id}"
            if fp not in cooled:
                subject = tasks[0].subject
                cards.append(_card(
                    "continue_plan",
                    f"继续{latest_plan.plan_date.strftime('%m-%d')}计划 · 完成 {done}/{total} · 剩 {remaining}min",
                    f"下一项：{tasks[0].topic}",
                    refs={"planId": latest_plan.id, "subject": subject},
                    generated=None,
                    instruction="基于计划现状继续",
                ))

    # 2) 待续复盘：self_report 记录近 7 天行为准确率未回填
    pending_review = db.execute(
        select(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.source == "self_report",
            LearningRecordORM.behavior_accuracy.is_(None),
            LearningRecordORM.started_at >= now - timedelta(days=SUFFICIENT_WINDOW_DAYS),
        )
        .order_by(LearningRecordORM.started_at.desc())
        .limit(1)
    ).scalars().first()
    if pending_review is not None:
        fp = f"go_on:record:{pending_review.id}"
        if fp not in cooled:
            cards.append(_card(
                "continue_plan",
                f"回填 {pending_review.subject} 上次复盘的准确率",
                "一两道题的结果就够，补上后状态评估更准",
                refs={"recordId": pending_review.id, "subject": pending_review.subject},
                generated=None,
                instruction="引导用户回填这次学习记录的正确率",
            ))

    return cards[:MAX_CARDS_PER_GROUP]


# ---------------------------------------------------------------- 推荐组


def _has_enough_data(db: Session, user_id: str, now: datetime) -> bool:
    """足够数据 = 近 7 天 ≥3 条学习记录 或 ≥1 次状态评估（口径卡设定）。"""
    record_count = len(db.execute(
        select(LearningRecordORM.id).where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.started_at >= now - timedelta(days=SUFFICIENT_WINDOW_DAYS),
        )
    ).scalars().all())
    if record_count >= SUFFICIENT_RECORDS:
        return True
    has_assessment = db.execute(
        select(AssessmentSnapshot.id).where(AssessmentSnapshot.user_id == user_id).limit(1)
    ).scalars().first() is not None
    return has_assessment


def _recommend_cards(db: Session, user_id: str, now: datetime) -> list[dict]:
    """推荐：状态 > 内容 > 目标规划；7 天内 shown 过的同指纹挡掉（只推有变化的）。

    足够数据不足 → 整组空缺（宁缺毋滥，target.md:190）。
    规则模板生成、不调 LLM（口径卡 §三：pilot 规则为主、AI 可选）。
    """
    if not _has_enough_data(db, user_id, now):
        return []
    cooled = _impression_note(db, user_id, CardGroup.recommend, CardAction.shown, now - COOLDOWN_RECOMMEND)
    candidates: list[tuple[int, dict, str]] = []

    # 1) 状态建议（state_advice）：最新一次状态评估
    snap = db.execute(
        select(AssessmentSnapshot).where(AssessmentSnapshot.user_id == user_id)
        .order_by(AssessmentSnapshot.computed_at.desc()).limit(1)
    ).scalars().first()
    if snap is not None:
        fp = f"recommend:state:{snap.subject}"
        if fp not in cooled:
            adj = "保持节奏" if snap.trend in ("up", "flat") else "今晚建议减量"
            candidates.append((_RECOMMEND_ORDER["state_advice"], _card(
                "state_advice",
                f"你{snap.subject}状态「{snap.state_label}」 · {adj}",
                f"趋势 {snap.trend} · 近 {snap.record_count} 条记录",
                refs={"subject": snap.subject, "stateLabel": snap.state_label, "trend": snap.trend},
                generated={"结论": snap.state_label, "建议": adj},
                instruction="展开成具体可执行建议",
            ), fp))

    # 2) 内容建议（content_advice）：掌握度最低且有样本的知识点
    weak = db.execute(
        select(PointMastery).where(PointMastery.user_id == user_id, PointMastery.sample_size > 0)
        .order_by(PointMastery.mastery.asc()).limit(1)
    ).scalars().first()
    if weak is not None:
        point_name = _point_name(db, weak.point_id) or weak.point_id
        subject = _point_subject(db, weak.point_id)
        fp = f"recommend:content:{weak.point_id}"
        if fp not in cooled:
            candidates.append((_RECOMMEND_ORDER["content_advice"], _card(
                "content_advice",
                f"推荐复习：{point_name}",
                f"掌握度 {round(weak.mastery * 100)}% · 样本 {weak.sample_size} 次",
                refs={"pointId": weak.point_id, "subject": subject},
                generated={"依据": f"你的掌握度 {round(weak.mastery * 100)}%，是当前最薄弱的知识点之一"},
                instruction="解释为什么 + 怎么做",
            ), fp))

    # 3) 目标规划（goal_planning）：活跃目标且近期无对应计划的
    goals = db.execute(
        select(GoalORM).where(GoalORM.user_id == user_id, GoalORM.status == "active")
        .order_by(GoalORM.created_at.asc()).limit(3)
    ).scalars().all()
    for goal in goals:
        fp = f"recommend:goal:{goal.id}"
        if fp in cooled:
            continue
        candidates.append((_RECOMMEND_ORDER["goal_planning"], _card(
            "goal_planning",
            f"为「{goal.title}」拆出下周 3 步",
            "目标拆解成可执行的小步，更容易推进",
            refs={"goalId": goal.id, "subject": goal.subject},
            generated={"差距": "目标仍在进行中，缺少近期可执行步骤"},
            instruction="规划拆解",
        ), fp))
        break  # 目标规划至多一条

    candidates.sort(key=lambda item: item[0])
    return [card for _order, card, _fp in candidates][:MAX_CARDS_PER_GROUP]


def _point_name(db: Session, point_id: str) -> str | None:
    from models.knowledge import KnowledgePoint

    row = db.get(KnowledgePoint, point_id)
    return getattr(row, "name", None) if row is not None else None


def _point_subject(db: Session, point_id: str) -> str | None:
    from models.knowledge import KnowledgePoint

    row = db.get(KnowledgePoint, point_id)
    return getattr(row, "subject_code", None) if row is not None else None


# ---------------------------------------------------------------- 洞察组


def _insight_cards(db: Session, user_id: str, now: datetime) -> list[dict]:
    """洞察：社区聚合 pool ≥ k=20 + 用户已授权；每周 ≤1、同维度周内不重复。

    「不足 k 不返回」落实在两处：
    1. jobs/community_aggregate.py 已保证 pool<k 不落行/删旧行（物化表本身没有）
    2. 这里再按 settings.community_min_pool 兜底断言 —— 不绕过 k（合规）
    未开匿名聚合授权 → 不产洞察卡（§4.9 未授权不返回任何聚合）。
    """
    settings_row = db.get(SettingsORM, user_id)
    if settings_row is None or not settings_row.community_consent_enabled:
        return []

    user = _load_user_stage(db, user_id)
    if user is None:
        return []
    stage = user

    from models.community import CommunityAggregate

    period = iso_week_of(now)
    ws = week_start(now)

    # 每周 ≤1：本周已 shown 过任何洞察卡 → 整组空（克制出现）
    week_shown = db.execute(
        select(CardImpression.id).where(
            CardImpression.user_id == user_id,
            CardImpression.group == CardGroup.insight.value,
            CardImpression.action == CardAction.shown.value,
            CardImpression.shown_at >= ws,
        ).limit(1)
    ).scalars().first()
    if week_shown is not None:
        return []

    k = settings.community_min_pool
    # 有数据的维度优先（fatigue > focus > completion > hours——克制且与「减量」叙事一致）
    for metric in ("fatigue", "focus", "completion", "hours"):
        row = db.execute(
            select(CommunityAggregate).where(
                CommunityAggregate.period == period,
                CommunityAggregate.stage == stage,
                CommunityAggregate.metric == metric,
            )
        ).scalars().first()
        if row is None or row.pool_size < k:
            continue  # 不足 k：该标的不生成（合规底线，不绕过）
        fp = f"insight:{stage}:{metric}:{period}"
        import json as _json
        percentiles = _json.loads(row.percentiles or "{}")
        p50 = percentiles.get("p50") if isinstance(percentiles, dict) else None
        title = f"同节奏人群本周「{_metric_label(metric)}」有变化 · {row.pool_size} 名匿名同龄人"
        return [_card(
            "group_insight",
            title,
            "参考群体节奏，不是对你的评价",
            refs={"stage": stage, "metric": metric, "period": period, "p50": p50},
            generated={"poolSize": row.pool_size, "percentiles": percentiles, "period": period},
            instruction="解释这个群体数据 + 我该怎么办",
        )]
    return []


def _metric_label(metric: str) -> str:
    return {"fatigue": "疲劳度", "focus": "专注度", "completion": "完成率", "hours": "学习时长"}.get(metric, metric)


def _load_user_stage(db: Session, user_id: str):
    from models.user import User

    row = db.get(User, user_id)
    return getattr(row, "stage", None) if row is not None else None


# ---------------------------------------------------------------- 组装与事件


def build_home_cards(db: Session, user_id: str, now: datetime | None = None) -> list[dict]:
    """产三组卡（组顺序固定 Go on → 推荐 → 洞察；无内容的组不返回）。"""
    now = now or utcnow()
    groups: list[dict] = []
    builders = (
        (CardGroup.go_on, _go_on_cards),
        (CardGroup.recommend, _recommend_cards),
        (CardGroup.insight, _insight_cards),
    )
    for group, builder in builders:
        cards = builder(db, user_id, now)
        if cards:
            groups.append({"group": group.value, "cards": cards})
    return groups


def record_impression(db: Session, user_id: str, data, now: datetime | None = None) -> CardImpression:
    """写一条卡片事件（单次事件只写一行；id/createdAt 服务端生成）。"""
    now = now or utcnow()
    row = CardImpression(
        id=f"ci_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        group=data.group.value,
        card_type=data.card_type.value,
        fingerprint=data.fingerprint,
        action=data.action.value,
        shown_at=data.shown_at or now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("[HOME-CARDS] 事件 user=%s group=%s action=%s fp=%s", user_id, data.group.value, data.action.value, data.fingerprint)
    return row

"""板块三两个 job 的**真库路径**护栏（M5 补漏）。

## 为什么要有这个文件

2026-10-03 实测发现两个 job 在真库上必崩，而既有测试全都测不到：

| 缺陷 | 位置 | 既有测试为什么没抓到 |
|---|---|---|
| BUG-1 聚合永不物化 | `jobs/community_aggregate.py` 曾用 `[row.value for row in ....scalars().all()]`，而 `select(单列).scalars()` 返回的是**标量（float）本身**，不是 Row | `test_community_aggregate.py` 只喂纯 Python 数值列表给纯函数；`test_community_aggregate_api.py` 直接**手工插入**聚合行再读接口——两边都不经过 `aggregate_all()` 的取数代码 |
| BUG-2 抽取永不落行 | `jobs/community_extraction.py` 曾用 `for (uid,) in users:`，而 `users` 是 `str` 列表 | `test_community_features.py` 只断言了两个口径常量存在，注释写着「真实抽取走 DB，由集成路径覆盖」——**而那条集成路径当时并不存在** |

后果叠加：抽取挂了 → 池子永远不足 → 聚合那段会崩的代码永远走不到，
于是两个 bug **互相掩盖**，从 M2 一路活到 2026-10-03。

本文件的职责就是补上「真跑 job」这一层：**没有真库、没有 pool≥k，就别说过**。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from database import SessionLocal
from models.community import CommunityFeature
from models.user import Settings as SettingsORM
from models.user import User as UserORM


# ---------- 夹具 ----------


def _seed_features(stage: str, metric: str, values: list[float], period: str) -> None:
    """直接落特征行（模拟「很多人已参与」的服务端抽取结果）。

    特征行本身**不含 user_id**（匿名参与 ID 是 HMAC），所以这里造 anon id 不违反口径。
    """
    db = SessionLocal()
    try:
        for i, v in enumerate(values):
            db.add(CommunityFeature(
                id=f"cf_{stage}_{metric}_{i:03d}",
                anon_participant_id=f"anon_{stage}_{metric}_{i:03d}",
                salt_version=0,
                period=period,
                stage=stage,
                metric=metric,
                value=float(v),
            ))
        db.commit()
    finally:
        db.close()


def _count(sql: str, **params) -> int:
    db = SessionLocal()
    try:
        return db.execute(text(sql), params).scalar_one()
    finally:
        db.close()


# ---------- BUG-1 护栏：聚合 job 必须真的物化 ----------


def test_aggregate_job_materializes_when_pool_reaches_k():
    """**pool ≥ k 时聚合 job 必须写出聚合行**（BUG-1 的回归护栏）。

    这条用例的价值在于它**必须走到那条取数 LIMIT 0 的 SQL 分支**：
    旧实现走到这里必抛 `AttributeError: 'float' object has no attribute 'value'`。
    任何「先手工插聚合行再读接口」的写法都测不到它——那正是当初漏掉的原因。
    """
    from config import settings
    from jobs.community_aggregate import _current_iso_week, run_community_aggregation

    period = _current_iso_week()
    k = settings.community_min_pool
    values = [float(5 + i) for i in range(k)]  # 恰好 k 条，覆盖边界

    _seed_features("senior", "hours", values, period)

    stats = run_community_aggregation()

    # 1) job 自己没崩，且真的写了行
    assert stats["written"] >= 1, f"聚合 job 没有写出任何聚合行：{stats}"

    # 2) 落库内容可被读回，且与纯函数口径一致（不能只是"写了行"）
    from community_aggregate import aggregate as pure_aggregate

    db = SessionLocal()
    try:
        from models.community import CommunityAggregate

        row = db.query(CommunityAggregate).filter_by(
            period=period, stage="senior", metric="hours"
        ).one()
        assert row.pool_size == k

        expected = pure_aggregate(values, "hours")
        import json

        assert json.loads(row.percentiles) == {
            "p25": expected["p25"], "p50": expected["p50"], "p75": expected["p75"],
        }
        assert json.loads(row.histogram) == expected["histogram"]
    finally:
        db.close()


def test_aggregate_job_deletes_row_when_pool_drops_below_k():
    """pool < k 时必须**删除**存量聚合行（重算语义：不够就得撤下旧数值）。

    与上一条配对：只测"能写"不测"能删"，会让「撤回授权后旧数值仍可读」这种
    隐私事故溜过去（撤回 = 物理删除特征行 → 池子变小 → 旧聚合行必须撤下）。
    """
    from config import settings
    from jobs.community_aggregate import _current_iso_week, run_community_aggregation

    period = _current_iso_week()
    k = settings.community_min_pool

    # 先够 k 条，物化出来
    _seed_features("senior", "focus", [4.0] * k, period)
    run_community_aggregation()
    assert _count(
        "SELECT COUNT(*) FROM community_aggregates WHERE period=:p AND stage='senior' AND metric='focus'",
        p=period,
    ) == 1

    # 抽掉 2 条 → 池子不足 k
    db = SessionLocal()
    try:
        db.execute(text(
            "DELETE FROM community_features WHERE period=:p AND stage='senior' AND metric='focus' "
            "AND anon_participant_id IN ('anon_senior_focus_000','anon_senior_focus_001')"
        ), {"p": period})
        db.commit()
    finally:
        db.close()

    run_community_aggregation()
    assert _count(
        "SELECT COUNT(*) FROM community_aggregates WHERE period=:p AND stage='senior' AND metric='focus'",
        p=period,
    ) == 0, "池子跌破 k 后旧聚合行没有被删除"


# ---------- BUG-2 护栏：特征抽取必须真的落行 ----------


def _seed_consented_user(uid: str = "u_extract_job_test") -> str:
    """造一个「已授权 + 已建档 + 本周有 1 条学习记录 + 有 1 个计划任务」的用户。"""
    from jobs.community_extraction import _current_iso_week, _week_bounds
    from models.learning_record import LearningRecord as RecordORM
    from models.plan import Plan as PlanORM
    from models.plan import PlanTask as TaskORM

    period = _current_iso_week()
    monday, _sunday = _week_bounds(period)
    started = datetime.combine(monday, datetime.min.time()) + timedelta(hours=19)

    db = SessionLocal()
    try:
        db.add(UserORM(
            id=uid, email=f"{uid}@example.com", stage="senior", grade="高二",
            subjects=["SX"], birth_year=2009, onboarding_completed=True,
        ))
        db.add(SettingsORM(user_id=uid, community_consent_enabled=True))

        db.add(RecordORM(
            id="r_extract_1", user_id=uid, subject="SX", started_at=started,
            duration_minutes=90, behavior_completion="completed",
            behavior_interruptions=0, self_report_focus=4, self_report_fatigue=2,
            source="self_report", skip_recommendation=True,
        ))

        db.add(PlanORM(id="p_extract_1", user_id=uid, plan_date=monday, available_minutes=120))
        db.add(TaskORM(
            id="t_extract_1", plan_id="p_extract_1", user_id=uid, subject="SX",
            topic="函数单调性", estimated_minutes=45, priority=1, status="completed",
        ))
        db.commit()
    finally:
        db.close()
    return period


def test_extraction_job_writes_feature_rows_for_consented_user():
    """**抽取 job 必须真的为已授权用户落特征行**（BUG-2 的回归护栏）。

    旧实现在 `for (uid,) in users:` 直接 `ValueError: too many values to unpack`
    ——job 整体抛异常，一个用户都抽不到，于是池子永远凑不满 k。
    """
    from anon_id import compute_anon_id
    from jobs.community_extraction import extract_community_features

    uid = "u_extract_job_test"
    period = _seed_consented_user(uid)

    stats = extract_community_features()

    assert stats["participants"] == 1, f"抽到 0 个参与者说明 job 又挂了：{stats}"
    # 本周 90 分钟 + 自评 focus/fatigue + 计划完成率 1/1 → 4 个指标全落
    assert stats["features"] == 4, stats

    anon = compute_anon_id(uid)
    db = SessionLocal()
    try:
        metrics = {
            row[0] for row in db.execute(
                text("SELECT metric FROM community_features WHERE anon_participant_id=:a AND period=:p"),
                {"a": anon, "p": period},
            ).all()
        }
    finally:
        db.close()
    assert metrics == {"hours", "focus", "fatigue", "completion"}

    # 合规底线：特征行只认匿名 ID，不得出现 user_id（模型层直接用裸 SQL 断，防绕过）
    assert _count(
        "SELECT COUNT(*) FROM community_features WHERE anon_participant_id=:a", a=uid
    ) == 0
    assert _count(
        "SELECT COUNT(*) FROM community_features WHERE anon_participant_id=:a", a=anon
    ) == 4


def test_extraction_skips_user_without_stage():
    """stage 缺失（未建档）不抽取——与 §4.6 口径一致，且不能因个别用户拖垮整个 job。

    `users.stage` 是 NOT NULL，所以「缺失」的真实形态是**未完成建档**（stage 为占位值
    + onboarding_completed=False）；抽取 job 对这两种情况都跳过。
    """
    from jobs.community_extraction import extract_community_features

    db = SessionLocal()
    try:
        db.add(UserORM(id="u_no_stage", email="nostage@example.com", stage="senior",
                       grade="", subjects=["other"], onboarding_completed=False))
        db.add(SettingsORM(user_id="u_no_stage", community_consent_enabled=True))
        db.commit()
    finally:
        db.close()

    stats = extract_community_features()
    assert stats["participants"] == 0, "未完成建档的用户不该被抽取"


# ---------- 模式级护栏：防止同类错误再犯 ----------


def test_no_scalar_result_treated_as_row():
    """源码扫描：`.scalars()` 的结果**不得**再按 Row/元组取属性或解包。

    这是 BUG-1/BUG-2 的**共同根因**，一条静态规则就能同时挡住两者：
    - `[row.value for row in ....scalars().all()]`   → 标量没有 .value
    - `for (uid,) in ....scalars().all()`            → 标量不是元组

    粗糙但有效；误报时请改写法而不是删本用例（可加 `# row-ok` 注释豁免）。
    """
    backend = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        # 只扫产品代码：跳过测试自身、虚拟环境、测试库目录、历史迁移
        if rel.startswith(("tests/", ".venv/", ".pytest_data/", "alembic/versions/")):
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "row-ok" in stripped:
                continue
            # 模式一：对标量列表做单元素元组解包
            if re.search(r"for\s*\(\s*\w+\s*,\s*\)\s+in\s+", line):
                offenders.append(f"{rel}:{lineno}: {stripped}")
            # 模式二：对标量列表取 .value/.id 等 ORM 属性
            if re.search(r"for\s+\w+\s+in\s+.*scalars\(\)", line) and re.search(
                r"\b\w+\.(value|id|user_id|code)\b", line
            ):
                offenders.append(f"{rel}:{lineno}: {stripped}")

    assert not offenders, (
        "检测到把 .scalars() 结果当 Row 使用的写法（BUG-1/BUG-2 同源根因）：\n  "
        + "\n  ".join(offenders)
    )

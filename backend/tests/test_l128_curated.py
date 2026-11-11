"""L128 · 精品样例入库可检索的测试（契约 v1.22.0 GET /explanations）。

## 核心断言（隐私边界，派单「最关键一例」）

`isCurated=false` 的动态生成**严格按当前用户隔离**——真实用户**查不到其他用户
的动态行**（修复前 list_explanations 硬过滤 `user_id == 当前用户`，系统账号
u_curated 的精品行永远查不到）。`isCurated=true` 只返回公共精品、
`isCurated=false` 只返回本人动态，`isCurated` 省略时两者都返回（同口径），
total 与 items 恒一致。

## seed 隔离

seed 通过 subprocess 跑真实脚本（与生产用法一致），DATABASE_URL 显式指向
conftest 的 .pytest_data/test.db——**不写共享开发库**（AGENTS §四·七）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from database import SessionLocal
from models.explanation import Explanation as ExplanationORM

BACKEND_DIR = Path(__file__).resolve().parents[1]
SEED_SCRIPT = BACKEND_DIR.parent / "scripts" / "seed_curated_explanations.py"
TEST_DB_URL = f"sqlite:///{(BACKEND_DIR / '.pytest_data' / 'test.db').as_posix()}"

UID = "u_real1"
OTHER_UID = "u_other2"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


def _run_seed() -> None:
    """跑真实 seed 脚本，DATABASE_URL 显式指向测试库（不碰共享开发库）。"""
    env = {**os.environ, "DATABASE_URL": TEST_DB_URL}
    subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        env=env, check=True, capture_output=True, text=True,
    )


def _mk_dynamic(db, uid: str, exp_id: str, subject: str = "SX", point_id: str | None = "kp_dyn_1") -> None:
    db.add(ExplanationORM(
        id=exp_id,
        user_id=uid,
        point_id=point_id,
        subject=subject,
        mode="regenerated",
        content=f"{uid} 的动态讲解（{exp_id}）",
        is_curated=False,
    ))
    db.commit()


def _get(client, uid: str, **params) -> dict:
    resp = client.get("/api/v1/explanations", params=params, headers={"X-User-ID": uid})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------- 核心隐私边界


def test_real_user_sees_curated_but_not_others_dynamic(client):
    """🔴 最关键一例：真实用户查得到 5 条公共精品，查不到其他用户的动态行。"""
    db = SessionLocal()
    try:
        _run_seed()
        # 别的用户的动态生成行（修复前：list_explanations 按 user_id 硬过滤，
        # 精品查不到；修法若写成无条件放开 user_id，别人的动态行就会漏出来）
        _mk_dynamic(db, OTHER_UID, "exp_other_dyn_1", subject="WL")
    finally:
        db.close()

    body = _get(client, UID)
    items = body["items"]

    curated = [i for i in items if i["isCurated"]]
    assert len(curated) == 5, "5 条公共精品样例应跨用户可见"
    assert all(i["explanationId"].startswith("exp_curated_") for i in curated)

    assert not any(i["explanationId"] == "exp_other_dyn_1" for i in items), \
        "其他用户的动态行绝不能出现（隐私边界失守）"

    # total 与 items 同一可见性口径
    assert body["pagination"]["total"] == len(items) == 5


def test_own_dynamic_rows_visible_and_others_hidden(client):
    """本人动态行可见 + 他人动态行不可见，两类同时存在时互不污染。"""
    db = SessionLocal()
    try:
        _run_seed()
        _mk_dynamic(db, UID, "exp_mine_1", subject="SX", point_id="kp_dyn_mine")
        _mk_dynamic(db, OTHER_UID, "exp_other_dyn_2", subject="SX", point_id="kp_dyn_mine")
    finally:
        db.close()

    body = _get(client, UID)
    ids = [i["explanationId"] for i in body["items"]]
    assert "exp_mine_1" in ids, "本人动态行应可见"
    assert "exp_other_dyn_2" not in ids, "他人动态行不可见"


# ---------------------------------------------------------------- isCurated 过滤


def test_is_curated_false_only_own_dynamic(client):
    """isCurated=false：只返回本人动态行，绝不能带出公共精品（也不带他人行）。"""
    db = SessionLocal()
    try:
        _run_seed()
        _mk_dynamic(db, UID, "exp_mine_dyn", subject="SX")
    finally:
        db.close()

    body = _get(client, UID, isCurated=False)
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["isCurated"] is False
    assert body["items"][0]["explanationId"] == "exp_mine_dyn"


def test_is_curated_true_only_public(client):
    """isCurated=true：只返回公共精品样例（无本人/他人动态行混入）。"""
    db = SessionLocal()
    try:
        _run_seed()
        _mk_dynamic(db, UID, "exp_mine_dyn2", subject="SX")
    finally:
        db.close()

    body = _get(client, UID, isCurated=True)
    items = body["items"]
    assert len(items) == 5
    assert all(i["isCurated"] is True for i in items)


# ---------------------------------------------------------------- 过滤与 total 一致


def test_subject_filter_and_total_consistency(client):
    db = SessionLocal()
    try:
        _run_seed()
    finally:
        db.close()

    body = _get(client, UID, subject="SX")
    assert body["pagination"]["total"] == 2  # 函数单调性 + 等差数列前 n 项和
    assert all(i["subject"] == "SX" for i in body["items"])

    body_all = _get(client, UID)
    assert body_all["pagination"]["total"] == len(body_all["items"]) == 5


def test_point_id_filter(client):
    db = SessionLocal()
    try:
        _run_seed()
    finally:
        db.close()

    from models.explanation import Explanation as ExplanationORM

    db = SessionLocal()
    try:
        row = db.query(ExplanationORM).filter(ExplanationORM.is_curated.is_(True)).first()
        pid = row.point_id
    finally:
        db.close()

    body = _get(client, UID, pointId=pid)
    assert body["pagination"]["total"] >= 1
    assert all(i["pointId"] == pid for i in body["items"])


# ---------------------------------------------------------------- seed 幂等


def test_seed_idempotent_no_duplicate_rows(client):
    """seed 幂等：连跑两次，精品行数不变（脚本按 (user,point,is_curated) upsert）。"""
    _run_seed()
    _run_seed()

    db = SessionLocal()
    try:
        rows = db.query(ExplanationORM).filter(ExplanationORM.is_curated.is_(True)).all()
        assert len(rows) == 5, f"幂等复跑不应产生重复精品行，实际 {len(rows)}"
        points = db.query(ExplanationORM.point_id).filter(
            ExplanationORM.is_curated.is_(True)
        ).distinct().count()
        assert points == 5
    finally:
        db.close()

"""Alembic 迁移的**空库 + 非空库双向**回归护栏（AGENTS.md §〇 授权要求）。

为什么需要这个文件：`a91f4c2d7e03` 曾把 `add_column(NOT NULL)` 与
`alter_column(server_default=None)` 放在**同一个** `batch_alter_table` 里，
在非空库上必然失败：

    sqlite3.IntegrityError: NOT NULL constraint failed:
    _alembic_tmp_settings.experience_improvement_enabled

机制：SQLite 的 batch 模式走「建临时表 → `INSERT INTO tmp SELECT`（**只带源表已有列**）
→ 删旧表 → 改名」。同一 batch 内先摘掉 `server_default` 后，重建出的临时表该列既没有
默认值、又不在 INSERT 列列表里，存量行于是拿到 NULL。

**为什么验收门没抓到**：「空库 `alembic upgrade head` 通过」在空库时 INSERT 插入 0 行、
不触发约束——所以只验空库是**不够**的。这与「本地库落后一迁移」「pytest 抓不到」同属
一类陷阱：验证路径没覆盖真实故障条件。

所以这里两条路径都跑，且都**预置数据**。只跑空库的护栏等于没有护栏。

用子进程 + 独立 `DATABASE_URL` 跑，真空库，不碰开发库 `data.db` 与
`.pytest_data/`，也不改动测试进程自身环境。
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import subprocess

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PY = BACKEND / ".venv/Scripts/python.exe"
if not PY.exists():  # 非本机布局（CI / Linux）退回当前解释器
    import sys

    PY = pathlib.Path(sys.executable)

HEAD = "a91f4c2d7e03"
PREV = "c7a1f2e4d9b3"


def _alembic(db: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    return subprocess.run(
        [str(PY), "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def _cols(db: pathlib.Path, table: str) -> list[str]:
    c = sqlite3.connect(db)
    try:
        return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
    finally:
        c.close()


def _version(db: pathlib.Path) -> str:
    c = sqlite3.connect(db)
    try:
        row = c.execute("select version_num from alembic_version").fetchone()
        return row[0] if row else ""
    except sqlite3.Error:
        return ""
    finally:
        c.close()


def _seed_nonempty(db: pathlib.Path) -> None:
    """预置一行 settings（关键：触发条件）+ 一行 users。

    5 个已有开关全设为 1，用来验证**重建过程没有把存量值抹掉**——
    batch_alter_table 是「重建表」，这类改动最容易悄悄丢数据。
    """
    c = sqlite3.connect(db)
    c.execute(
        "INSERT INTO settings (user_id, ai_weight_tuning_enabled, send_text_to_ai,"
        " knowledge_ai_egress_enabled, community_consent_enabled,"
        " community_auto_participate, updated_at)"
        " VALUES ('u_seed', 1, 1, 1, 1, 1, CURRENT_TIMESTAMP)"
    )
    c.execute(
        "INSERT INTO users (id, stage, grade, subjects, onboarding_completed,"
        " created_at, updated_at, email, handle)"
        " VALUES ('u_seed','junior','初二','[\"SX\"]',1,CURRENT_TIMESTAMP,"
        "CURRENT_TIMESTAMP,'seed@example.com','seed')"
    )
    c.commit()
    c.close()


@pytest.fixture
def db_at_head(tmp_path: pathlib.Path) -> pathlib.Path:
    """一个已经升到 head 的临时库。"""
    db = tmp_path / "head.db"
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, f"基线 upgrade head 失败：{(r.stderr or r.stdout)[-400:]}"
    return db


@pytest.fixture
def db_at_prev(tmp_path: pathlib.Path) -> pathlib.Path:
    """一个升到 head 的前一个版本、且尚无数据的临时库。"""
    db = tmp_path / "prev.db"
    r = _alembic(db, "upgrade", PREV)
    assert r.returncode == 0, f"基线 upgrade {PREV} 失败：{(r.stderr or r.stdout)[-400:]}"
    return db


# ---------- 非空库：原 bug 的触发条件，最重要的一条 ----------


def test_upgrade_head_on_nonempty_db(db_at_prev: pathlib.Path):
    """🔴 非空库（settings 有行）升到 head 必须成功。

    这是 `a91f4c2d7e03` 的回归守卫。原实现在此必失败
    （NOT NULL constraint failed: _alembic_tmp_settings.…）。
    """
    _seed_nonempty(db_at_prev)
    r = _alembic(db_at_prev, "upgrade", "head")
    assert r.returncode == 0, f"非空库 upgrade head 失败：{(r.stderr or r.stdout)[-400:]}"
    assert _version(db_at_prev) == HEAD


def test_upgrade_preserves_existing_settings_values(db_at_prev: pathlib.Path):
    """batch 重建不得抹掉存量开关值，且新列对存量行落默认（opt-in = 关）。"""
    _seed_nonempty(db_at_prev)
    assert _alembic(db_at_prev, "upgrade", "head").returncode == 0

    c = sqlite3.connect(db_at_prev)
    try:
        kept = c.execute(
            "SELECT ai_weight_tuning_enabled, send_text_to_ai, knowledge_ai_egress_enabled,"
            " community_consent_enabled, community_auto_participate FROM settings"
        ).fetchall()
        new = c.execute(
            "SELECT user_id, experience_improvement_enabled FROM settings"
        ).fetchall()
    finally:
        c.close()

    assert kept == [(1, 1, 1, 1, 1)], f"重建抹掉了存量开关值：{kept}"
    assert new == [("u_seed", 0)], f"新列未按 opt-in 落 0：{new}"


def test_nonempty_downgrade_to_base(db_at_prev: pathlib.Path):
    """非空库也能 downgrade 回 base（重建表同样不能丢数据）。"""
    _seed_nonempty(db_at_prev)
    assert _alembic(db_at_prev, "upgrade", "head").returncode == 0
    r = _alembic(db_at_prev, "downgrade", "base")
    assert r.returncode == 0, f"downgrade 失败：{(r.stderr or r.stdout)[-400:]}"
    assert "experience_improvement_enabled" not in _cols(db_at_prev, "settings")
    assert "birth_year" not in _cols(db_at_prev, "users")


# ---------- 空库：原实现「恰好能过」的那条路径也得守住 ----------


def test_upgrade_head_on_empty_db(db_at_head: pathlib.Path):
    """空库链路：加列到位。"""
    assert "birth_year" in _cols(db_at_head, "users")
    assert "experience_improvement_enabled" in _cols(db_at_head, "settings")


def test_empty_db_downgrade_then_upgrade_again(db_at_head: pathlib.Path):
    """空库 upgrade → downgrade base → 再 upgrade 必须仍然干净。"""
    assert _alembic(db_at_head, "downgrade", "base").returncode == 0
    assert "birth_year" not in _cols(db_at_head, "users")
    r = _alembic(db_at_head, "upgrade", "head")
    assert r.returncode == 0, f"二次 upgrade 失败：{(r.stderr or r.stdout)[-400:]}"
    assert "experience_improvement_enabled" in _cols(db_at_head, "settings")


def test_alembic_check_reports_no_drift(db_at_head: pathlib.Path):
    """`alembic check` 干净——保证摘掉 server_default 后仍与 ORM 元数据一致。"""
    r = _alembic(db_at_head, "check")
    combined = r.stdout + r.stderr
    assert r.returncode == 0 and "No new upgrade operations" in combined, combined[-400:]


def test_repeated_upgrade_is_idempotent(db_at_head: pathlib.Path):
    """已在 head 再 upgrade：不得重复加列、不得重复加行。"""
    c = sqlite3.connect(db_at_head)
    c.execute(
        "INSERT INTO settings (user_id, ai_weight_tuning_enabled, send_text_to_ai,"
        " knowledge_ai_egress_enabled, community_consent_enabled,"
        " community_auto_participate, updated_at, experience_improvement_enabled)"
        " VALUES ('u_seed',1,1,1,1,1,CURRENT_TIMESTAMP,0)"
    )
    c.commit()
    c.close()

    assert _alembic(db_at_head, "upgrade", "head").returncode == 0
    assert _cols(db_at_head, "settings").count("experience_improvement_enabled") == 1
    c = sqlite3.connect(db_at_head)
    try:
        assert c.execute("select count(*) from settings").fetchone()[0] == 1
    finally:
        c.close()


# ---------- 跨方言：默认值渲染（Postgres 特有缺陷，SQLite 测不出）----------


def test_boolean_server_default_is_dialect_portable():
    """🔴 BOOLEAN 列的 server_default 必须用 `sa.false()`，不能用 `sa.text('0')`。

    Postgres **拒绝**给 BOOLEAN 列配 `DEFAULT 0`：
        psycopg2.errors.DatatypeMismatch: column "experience_improvement_enabled"
        is of type boolean but default expression is of type integer
    SQLite 动态类型照单全收 → 只在 SQLite 上验是**测不出来的**。

    2026-10-01 在 Neon 生产升级时实际触发过此错误（已回滚干净，因为 PG 有事务型 DDL）。
    本用例直接断言两种方言下的渲染结果，把这条差异钉在测试里。
    """
    import sqlalchemy as sa

    sqlite_dialect = sa.create_engine("sqlite://").dialect
    pg_dialect = sa.create_engine("postgresql://").dialect

    ok = sa.Column("x", sa.Boolean(), nullable=False, server_default=sa.false())
    assert str(ok.server_default.arg.compile(dialect=sqlite_dialect)).strip() == "0"
    assert str(ok.server_default.arg.compile(dialect=pg_dialect)).strip() == "false"

    # 反证：sa.text('0') 在两种方言下都渲染成 0 —— 这就是 PG 报错的原因
    bad = sa.text("0")
    assert str(bad.compile(dialect=sqlite_dialect)).strip() == "0"
    assert str(bad.compile(dialect=pg_dialect)).strip() == "0"


def test_migration_uses_portable_boolean_default():
    """直接检查迁移源码不含 `sa.text('0')` 这类非可移植默认值。"""
    import re

    src = (
        BACKEND / "alembic/versions/a91f4c2d7e03_a_identity_birthyear_improvement.py"
    ).read_text(encoding="utf-8")
    offenders = re.findall(r"server_default\s*=\s*sa\.text\(", src)
    assert not offenders, "迁移里出现 sa.text() 形式的 server_default，Postgres 会拒绝"

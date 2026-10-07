"""Neon（Postgres）外部逻辑备份 —— 纯 Python 实现，不依赖 pg_dump / docker。

为什么需要这个（2026-10-04）：
Neon 免费版（`subscription_type=free_v3`）**两个能力都没有**——
- 只允许 **1 个手动快照**（实测 `snapshots limit exceeded`）
- **不支持自动备份计划**（实测 `backup schedule creation is not enabled for this project`）
所以「每次生产写操作前打快照」在当前套餐下做不到：唯一的名额还被迁移前的快照占着。
PITR 只有 6h（`history_retention_seconds=21600`），窗口太短。

外部逻辑备份是不占 Neon 名额、免费版可用的唯一无限制回退手段。

## 关于那个手动快照（重要，2026-10-04 lead-1 裁定）

项目里现有 1 个手动快照 `pre-alembic-a91f4c2d7e03-20261001`：

- **它只为一件事存在：兜「迁移本身写错了」。**
  迁移虽已做三向复验（空库 SQLite + 非空库 SQLite + Postgres），但那验证覆盖不了
  「迁移逻辑本身写错」这种情况——三向都按同一份错误代码跑，会一致地错。
- **它不是日常备份，也不会自动更新。** 它是 2026-10-01 的静态快照，
  之后就再没变过；把它当「当前库的备份」用会拿到过期数据。
- **日常备份与回退靠本脚本。** 免费版手动快照只有 1 个名额，被它占着，
  所以任何生产写操作前都打不出新快照——这正是本脚本存在的原因。
- **不要删它。**（lead-1 2026-10-04 采纳 dev-4 的倾向：暂留不删。）

设计要点：
- **只读**：全程只发 SELECT / 查元数据，`set_session(readonly=True)` 兜底，绝不写库。
- **不打印连接串**：从环境变量 `DATABASE_URL` 读，缺失即报错退出；不接受命令行传连接串。
- **转义交给服务端**：用 SQL 里的 `quote_nullable(col)` 逐列生成字面量，
  让 PostgreSQL 用自己的编码做转义（这正是 pg_dump 的做法）。
  **不要改用客户端 `psycopg2.extensions.adapt()`** —— 实测在中文内容上：
  `adapt(str, conn)` 抛 `can't adapt type 'str'`，`adapt(str)` 抛
  `UnicodeEncodeError: 'latin-1' codec can't encode characters`。那是个陷阱。
- **拓扑排序建表顺序**：按 `pg_constraint` 外键依赖做拓扑序，
  不依赖 `session_replication_role=replica`（需 superuser，Neon owner 未必有）。
- **序列**在建表数据后统一 `setval` 复原，避免恢复后主键撞车。
  注意 `pg_sequences` **没有 `is_called` 列**，必须直接查序列关系。
- **自校验**：写完报告文件大小 / 表数 / 总行数 + SHA-256。

已验证前提：本库**无 bytea 列**（`information_schema` 实测），故 `quote_nullable`
的文本化对所有列都���往返。若将来新增 bytea 列需重新评估。

用法：
    # PowerShell
    $env:DATABASE_URL = "postgresql://..."
    .venv\\Scripts\\python.exe ../scripts/backup_neon.py
    # 保留最近 7 份，删更旧的（删备份需显式 --keep）
    .venv\\Scripts\\python.exe ../scripts/backup_neon.py --keep 7

⚠️ 备份文件**含生产数据**，输出目录已在 .gitignore 里（`.backups/`）。
   不要把它加进版本库，也不要贴进交付文档或聊天记录。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DEFAULT_OUT_DIR = BACKEND_DIR / ".backups" / "neon"

PRELUDE = """\
-- 由 scripts/backup_neon.py 生成（纯 Python 逻辑备份，非 pg_dump）
-- 生成时间(UTC): {ts}
--
-- ⚠️ 本文件是 **纯数据备份（data-only）**，不含 CREATE TABLE。
--    灌进**空库**会报 relation does not exist —— 那是预期的，不是备份坏了。
--
-- 恢复步骤（顺序不能反）：
--    1) 建库并把 schema 建起来：alembic upgrade head
--       （schema 的唯一真相源是迁移链；空库 upgrade 已做三向复验）
--    2) 再灌本文件：psql "$DATABASE_URL" -f 本文件
--    3) 校验：SELECT count(*) FROM kb_points; 应为 3391
--
-- 也可直接灌进 schema 已存在的库（Neon 从快照/PITR 恢复后即是），
-- 此时只需第 2、3 步。
--
-- 注意: 本文件含生产数据，勿提交版本库、勿外传。
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
BEGIN;
"""

EPILOGUE_TMPL = """\
COMMIT;
-- alembic_version: {alembic}
"""


def _get_tables(conn) -> list[str]:
    """public schema 的基表。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [r[0] for r in cur.fetchall()]


def _quote_ident(conn, name: str) -> str:
    """标识符加双引号（大小写敏感 / 保留字安全）。"""
    with conn.cursor() as cur:
        cur.execute("SELECT quote_ident(%s)", (name,))
        return cur.fetchone()[0]


def _quote_idents(conn, names: list[str]) -> list[str]:
    """批量 quote_ident。"""
    with conn.cursor() as cur:
        cur.execute("SELECT quote_ident(x) FROM unnest(%s::text[]) AS t(x)", (names,))
        return [r[0] for r in cur.fetchall()]


def _topo_sort_tables(conn, tables: list[str]) -> list[str]:
    """按外键依赖拓扑排序：被引用的表先插入。

    无环时返回全序；有环时把剩余表按名字追加在后面并警告——
    宁可顺序不完美也不要丢表。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT child.relname, parent.relname
            FROM pg_constraint con
            JOIN pg_class child  ON child.oid  = con.conrelid
            JOIN pg_class parent ON parent.oid = con.confrelid
            WHERE con.contype = 'f'
              AND child.relnamespace  = 'public'::regnamespace
              AND parent.relnamespace = 'public'::regnamespace
            """
        )
        edges = [(c, p) for c, p in cur.fetchall() if c in tables and p in tables]

    deps: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in edges:
        deps[child].add(parent)

    ordered: list[str] = []
    temp = set(tables)
    while temp:
        ready = sorted(t for t in temp if not (deps[t] & temp))
        if not ready:
            rest = sorted(temp)
            print(
                f"[警告] 外键依赖存在环，剩余 {len(rest)} 张表按名字顺序追加：{rest}",
                file=sys.stderr,
            )
            ordered.extend(rest)
            break
        ordered.extend(ready)
        temp -= set(ready)
    return ordered


def _dump_table(conn, table: str, out) -> int:
    """写出一张表的 INSERT 语句，返回行数。

    用服务端 `quote_nullable()` 逐列生成字面量再拼成整条 INSERT：
    转义与编码全部由 PostgreSQL 负责，一次往返取回整表。
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {_quote_ident(conn, table)}")
        cols = [d[0] for d in cur.description]
        if not cols:
            return 0

        q_table = _quote_ident(conn, table)
        q_cols = _quote_idents(conn, cols)
        col_list = ", ".join(q_cols)
        # 每列用 quote_nullable 包一层：NULL -> 未加引号的 NULL；其余 -> 正确转义并加引号。
        # 值全是text 且 quote_nullable 永不返回 SQL NULL，故 || 不会把整条表达式变成 NULL。
        # 列名必须用 quote_ident 过的形式——库里有保留字列名（如 community_features.group），
        # 直接写 quote_nullable(group) 会 syntax error。
        expr = " || ',' || ".join(f"quote_nullable({q})" for q in q_cols)
        sql = (
            f"SELECT 'INSERT INTO {q_table} ({col_list}) VALUES (' || {expr} || ');' "
            f"FROM {q_table}"
        )
        cur.execute(sql)
        rows = 0
        for (line,) in cur:
            out.write(line + "\n")
            rows += 1
    return rows


def _dump_sequences(conn, out) -> int:
    """复原序列当前值（恢复后主键不撞车的关键）。

    直接查序列关系而不是 pg_sequences —— 后者没有 `is_called` 列。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
            ORDER BY sequencename
            """
        )
        seqs = [r[0] for r in cur.fetchall()]
        count = 0
        for seq in seqs:
            q_seq = _quote_ident(conn, seq)
            cur.execute(f"SELECT last_value, is_called FROM public.{q_seq}")
            row = cur.fetchone()
            if not row:
                continue
            last_value, is_called = row
            out.write(
                f"SELECT setval('{q_seq}', {int(last_value)}, "
                f"{'true' if is_called else 'false'});\n"
            )
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Neon 外部逻辑备份（纯 Python）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="输出目录")
    parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help="只保留最近 N 份、删更旧的（不传则全留）。删备份需显式指定。",
    )
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print(
            "[中止] 未设置 DATABASE_URL 环境变量。\n"
            "  本脚本不接受命令行传连接串（会进 shell 历史与进程列表）。\n"
            "  PowerShell 用法: $env:DATABASE_URL = 'postgresql://...'",
            file=sys.stderr,
        )
        return 2
    if url.startswith("sqlite"):
        print("[中止] DATABASE_URL 指向 SQLite，本脚本只备份 Postgres。", file=sys.stderr)
        return 2

    try:
        import psycopg2
    except ImportError:
        print(
            "[中止] 需要 psycopg2：用 backend\\.venv\\Scripts\\python.exe 跑本脚本。",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"neon-{stamp}.sql"

    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    total_rows = 0
    try:
        with conn:
            tables = _get_tables(conn)
            ordered = _topo_sort_tables(conn, tables)
            print("目标: Neon Postgres（连接串不打印）")
            print(f"表数量: {len(ordered)}")
            print(f"输出到: {out_path}")

            with open(out_path, "w", encoding="utf-8", newline="\n") as out:
                out.write(PRELUDE.format(ts=stamp))
                for i, table in enumerate(ordered, 1):
                    # alembic_version 不转储：恢复第1 步（alembic upgrade head）已经
                    # 把它设成 head 了，再插一行会撞主键。它的当前值记在文件末尾注释里。
                    if table == "alembic_version":
                        with conn.cursor() as cur:
                            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
                            row = cur.fetchone()
                            alembic = row[0] if row else "(空)"
                        print(f"  [{i}/{len(ordered)}] {table:<32} {'(不转储)':>9}")
                        continue
                    rows = _dump_table(conn, table, out)
                    total_rows += rows
                    print(f"  [{i}/{len(ordered)}] {table:<32} {rows:>7} 行")
                seqs = _dump_sequences(conn, out)
                out.write(EPILOGUE_TMPL.format(alembic=alembic))
    finally:
        conn.close()

    size = out_path.stat().st_size
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()

    print()
    print("=== 备份完成 ===")
    print(f"  文件      {out_path}")
    print(f"  大小      {size:,} bytes")
    print(f"  总行数    {total_rows:,}")
    print(f"  序列复原  {seqs} 条")
    print(f"  SHA-256   {digest}")
    print()
    print("  [!] 该文件含生产数据：已在 .gitignore 中，但仍需自行控制留存与副本数量。")

    if args.keep is not None and args.keep > 0:
        dumps = sorted(out_dir.glob("neon-*.sql"))
        old = dumps[: max(0, len(dumps) - args.keep)]
        for path in old:
            path.unlink()
            print(f"  已删旧备份 {path.name}")
        if old:
            print(f"  保留最近 {args.keep} 份")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""移除 kb_point_mastery 上与主键完全重复的 UNIQUE 约束（方言守卫）

Revision ID: b7d2e4f1a609
Revises: a91f4c2d7e03
Create Date: 2026-10-01

## 为什么有这个迁移

`kb_point_mastery` 的主键就是 `(user_id, point_id)`，而基线 `1a6f0c6bb285` 又声明了
一个**同样两列**的 `CONSTRAINT uq_user_point UNIQUE`。二者语义完全等价，该 UNIQUE
是纯冗余。

它造成的实际后果是**方言相关的 schema 漂移**，让 `alembic check` 在 Postgres 上永远
不干净：

    ERROR: New upgrade operations detected: [('add_constraint',
        UniqueConstraint(user_id, point_id, table=kb_point_mastery))]

—— 模型里有、库里没有（Postgres 视角）。于是任何人对着 Neon 跑
`alembic revision --autogenerate` 都会生成一个「加这个约束」的迁移，而 Postgres
又会静默丢弃它，形成无法收敛的循环 no-op。

## ⚠️ 为什么这个迁移必须按方言分支

**在 PostgreSQL 上，名为 `uq_user_point` 的约束就是主键本身。** 实测（Neon 生产）：

    conname      | contype | 定义
    uq_user_point|    p    | PRIMARY KEY (user_id, point_id)   <-- 是主键
    独立 UNIQUE 数量：0

PostgreSQL 在 `CREATE TABLE` 时发现该 UNIQUE 与既有主键列完全相同，按其规范
**静默跳过**（不报错），并把主键保留为这个具名约束。结果就是：
无条件执行 `DROP CONSTRAINT uq_user_point` **等于删掉主键**，会直接破坏数据完整性。

而 SQLite 两边都留着：反射能读到独立的 `uq_user_point`，可以用 batch 模式重建去掉。

故本迁移：**Postgres 直接跳过（无事可做，冗余约束已被 PG 消除），SQLite 才重建去掉。**

## 为什么不动基线

基线 `1a6f0c6bb285` 保持原样。四种库的收敛结果都是「只剩主键」：

| 库 | 基线建出 | 本迁移 | 结果 |
|---|---|---|---|
| 新建 SQLite | PK + 冗余 UNIQUE | 去掉 UNIQUE | PK ✅ |
| 已有 SQLite（本地 / 队友） | 同上 | 去掉 UNIQUE | PK ✅ |
| 新建 Postgres | PK（PG 已折叠） | 跳过 | PK ✅ |
| 已有 Postgres（Neon） | PK | 跳过 | PK ✅ |

改基线会让「新建的库」与「已存在的库」结构分叉，代价大于收益。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2e4f1a609"
down_revision: Union[str, None] = "a91f4c2d7e03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "kb_point_mastery"
REDUNDANT = "uq_user_point"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Postgres：冗余约束已被 PG 折叠进主键，且该名字**就是主键**。
    # 此处必须跳过——DROP 掉它等于删主键。
    if _is_postgres():
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(REDUNDANT, type_="unique")


def downgrade() -> None:
    # 回到基线形态（仅 SQLite 能真正持有这个冗余约束；PG 加了也会被静默丢弃）
    if _is_postgres():
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.create_unique_constraint(REDUNDANT, ["user_id", "point_id"])

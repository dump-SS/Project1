"""A 板块 M1：出生年份（D40/D41 低龄门槛）+「用于提升体验」开关（#29b）

Revision ID: a91f4c2d7e03
Revises: c7a1f2e4d9b3
Create Date: 2026-09-30

**为什么改**（对应契约 v1.8.0，A 板块「身份、入口与合规」）：

1. **`users.birth_year`（可空）**——D41 要求「<14 岁建档强制监护人授权」，
   而此前 users 表**没有任何年龄信息**，门槛无从判定。采集出生年份而非布尔
   `under14`：周岁随年份自然增长（今天 13 岁、明年 14 岁，用布尔会写死），
   且不引入精确生日的过度采集（最小必要）。可空是为了不破坏既有无 birthYear
   数据：判定侧按「缺失不拦截」处理。
2. **`settings.experience_improvement_enabled`（NOT NULL，默认 0）**——#29b
   「将个人数据用于提升体验」开关，**默认关闭（opt-in）**。存量行必须有值，
   故先带 `server_default` 落 0、再摘掉 server_default，与 ORM 的 Python 侧
   `default=False` 保持一致（否则 `alembic check` 会报差异——同 c7a1f2e4d9b3 的教训）。

⚠️ 迁移文件按团队约定归 X0 合并（本文件由 A 板块随 PR 提交，待 X0 评审）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a91f4c2d7e03'
down_revision: Union[str, None] = 'c7a1f2e4d9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        # D40 激活式建档采集；D41 低龄门槛判定用
        batch_op.add_column(sa.Column('birth_year', sa.Integer(), nullable=True))

    # ---- settings.experience_improvement_enabled：必须拆成两个 batch ----
    #
    # ⚠️ 2026-10-01 修复：原实现把 add_column 与「摘掉 server_default」放在**同一个**
    # `batch_alter_table` 里，在**非空库**上必然失败：
    #   sqlite3.IntegrityError: NOT NULL constraint failed:
    #   _alembic_tmp_settings.experience_improvement_enabled
    #
    # 机制：SQLite 的 batch 模式没有真 ALTER，走「建临时表 → INSERT INTO tmp SELECT
    # （**该 INSERT 只带源表已有列，不含新加的列**）→ 删旧表 → 改名」。同一个 batch 内
    # 先 `alter_column(server_default=None)` 后重建出的临时表，该列既没有默认值、
    # 又不在 INSERT 列表里，存量行于是拿到 NULL，违反 NOT NULL。
    #
    # 为什么之前没被发现：**空库时 INSERT 插入 0 行，不触发约束**——所以
    # 「空库 `alembic upgrade head` 通过」这道验收门完全抓不到它。
    # （与「本地库落后一迁移」「pytest 抓不到」同属一类陷阱：验收门只验了空库。）
    #
    # 修法：拆成两个 batch。阶段 1 的临时表带 `server_default='0'`，INSERT 省略该列时
    # 由默认值兜住，存量行落 0；阶段 2 再重建一次摘默认值——此时该列已存在于 `settings`，
    # 重建时的 INSERT 会带上真实值，不再有 NULL 可写。
    with op.batch_alter_table('settings', schema=None) as batch_op:
        # #29b：先带默认值落值（存量行 = 关闭）
        batch_op.add_column(
            sa.Column(
                'experience_improvement_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('0'),
            )
        )

    with op.batch_alter_table('settings', schema=None) as batch_op:
        # 再摘 server_default，与 ORM 的 Python 侧 default=False 保持一致
        # （否则 `alembic check` 会报差异——同 c7a1f2e4d9b3 的教训）
        batch_op.alter_column('experience_improvement_enabled', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('experience_improvement_enabled')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('birth_year')

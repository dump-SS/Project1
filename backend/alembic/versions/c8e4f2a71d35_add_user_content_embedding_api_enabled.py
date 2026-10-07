"""add settings user_content_embedding_api_enabled column (PRD 12.6 / D41)

Revision ID: c8e4f2a71d35
Revises: b7d2e4f1a609
Create Date: 2026-10-05

用户内容（错题原文 / 作答 / 学习记录）的 embedding 是否允许走第三方 API。
默认 false（opt-in）：关闭时恒定走本地模型。

⚠️ 两条本仓库踩过的坑，这里都刻意避开：
1. 布尔列默认值用 ``sa.false()``，**不用** ``sa.text('0')``——
   ``sa.text('0')`` 落在 BOOLEAN 列上 PG 会报 DatatypeMismatch，而 SQLite 动态类型照单全收、
   本地 100% 测不出来（见 AGENTS.md §四·六）。``sa.false()`` 由各方言各自编译（SQLite 出 0、PG 出 false）。
2. **不摘默认值**：不把 ``add_column(NOT NULL, server_default=...)`` 与
   ``alter_column(server_default=None)`` 放进同一个 ``batch_alter_table`` ——
   SQLite batch 模式走「建临时表 → INSERT INTO tmp SELECT（不含新列）→ 改名」，
   摘掉默认值后存量行拿 NULL、违 NOT NULL；空库时插 0 行不触发（同上）。

照先例：``alembic/versions_archive/b3c2d1e4a5f6_add_settings_egress_column.py``（同表同类布尔列）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c8e4f2a71d35'
down_revision: Union[str, None] = 'b7d2e4f1a609'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column(
            'user_content_embedding_api_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('settings', 'user_content_embedding_api_enabled')

"""add auth_rate_limits table (auth 限流与失败锁定持久化)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-15

背景：auth/rate_limit.py 原为进程内 dict，多实例下「连续失败 5 次锁定」
退化成 5×N 次，重启清零。改为读写本表（不引 Redis）。

注意：本仓库当前以 create_all 为 schema 唯一真相源，本迁移仅作留痕，
勿单独执行 upgrade head（见 backend/README.md 与 commit 0058917）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auth_rate_limits',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('scope', sa.String(16), nullable=False),
        sa.Column('bucket_key', sa.String(320), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('scope', 'bucket_key', name='uq_auth_rate_limit'),
    )
    op.create_index('ix_auth_rate_limits_scope', 'auth_rate_limits', ['scope'])
    op.create_index('ix_auth_rate_limits_bucket_key', 'auth_rate_limits', ['bucket_key'])


def downgrade() -> None:
    op.drop_table('auth_rate_limits')

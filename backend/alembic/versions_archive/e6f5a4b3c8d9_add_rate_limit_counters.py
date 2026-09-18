"""add rate_limit_counters table (板块二 S0-T5 限流持久化)

Revision ID: e6f5a4b3c8d9
Revises: a6b5c4d3e2f1
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e6f5a4b3c8d9'
down_revision: Union[str, None] = 'a6b5c4d3e2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rate_limit_counters',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('bucket_key', sa.String(64), nullable=False),
        sa.Column('bucket_date', sa.DateTime(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'bucket_key', 'bucket_date', name='uq_rate_limit_bucket'),
    )
    op.create_index('ix_rate_limit_counters_user_id', 'rate_limit_counters', ['user_id'])
    op.create_index('ix_rate_limit_counters_bucket_key', 'rate_limit_counters', ['bucket_key'])


def downgrade() -> None:
    op.drop_table('rate_limit_counters')

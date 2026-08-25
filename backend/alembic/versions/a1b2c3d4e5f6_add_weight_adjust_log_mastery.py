"""add mastery weight snapshot columns to weight_adjust_logs (板块二 S0-T6)

Revision ID: a1b2c3d4e5f6
Revises: f7012345abcd
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7012345abcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for prefix in ('before', 'after'):
        for col in ('m1', 'm2', 'm3', 'm4', 'm5'):
            op.add_column('weight_adjust_logs', sa.Column(f'{prefix}_{col}', sa.Float(), nullable=True))


def downgrade() -> None:
    for prefix in ('before', 'after'):
        for col in ('m1', 'm2', 'm3', 'm4', 'm5'):
            op.drop_column('weight_adjust_logs', f'{prefix}_{col}')

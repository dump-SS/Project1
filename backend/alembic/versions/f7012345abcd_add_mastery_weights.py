"""add mastery content weights m1-m5 (板块二 S0-T6)

Revision ID: f7012345abcd
Revises: e6f5a4b3c8d9
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f7012345abcd'
down_revision: Union[str, None] = 'e6f5a4b3c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in ('m1', 'm2', 'm3', 'm4', 'm5'):
        op.add_column('user_weight_configs', sa.Column(col, sa.Float(), nullable=False, server_default='0.2'))


def downgrade() -> None:
    for col in ('m1', 'm2', 'm3', 'm4', 'm5'):
        op.drop_column('user_weight_configs', col)

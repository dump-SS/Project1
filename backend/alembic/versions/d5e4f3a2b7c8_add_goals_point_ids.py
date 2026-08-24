"""add goals point_ids column (板块二 v2.2)

Revision ID: d5e4f3a2b7c8
Revises: c4d3e2f1a6b7
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd5e4f3a2b7c8'
down_revision: Union[str, None] = 'c4d3e2f1a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('goals', sa.Column('point_ids', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('goals', 'point_ids')

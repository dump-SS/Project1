"""add summaries dimension column (板块二 v2.2 知识复盘)

Revision ID: c4d3e2f1a6b7
Revises: b3c2d1e4a5f6
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d3e2f1a6b7'
down_revision: Union[str, None] = 'b3c2d1e4a5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'summaries',
        sa.Column('dimension', sa.String(32), nullable=False, server_default='state_and_plan'),
    )


def downgrade() -> None:
    op.drop_column('summaries', 'dimension')

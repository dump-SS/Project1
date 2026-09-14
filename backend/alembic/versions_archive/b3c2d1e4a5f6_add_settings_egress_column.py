"""add settings knowledge_ai_egress_enabled column (PRD 12.6)

Revision ID: b3c2d1e4a5f6
Revises: 9ea1c2e3b7f4
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c2d1e4a5f6'
down_revision: Union[str, None] = '9ea1c2e3b7f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column('knowledge_ai_egress_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('settings', 'knowledge_ai_egress_enabled')

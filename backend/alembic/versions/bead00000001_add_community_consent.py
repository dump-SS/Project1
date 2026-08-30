"""add community consent columns (板块三 M1)

Revision ID: bead00000001
Revises: c0ffee123456
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'bead00000001'
down_revision: Union[str, None] = 'c0ffee123456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('settings', sa.Column('community_consent_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('settings', sa.Column('community_auto_participate', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('settings', 'community_auto_participate')
    op.drop_column('settings', 'community_consent_enabled')

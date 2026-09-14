"""add content fields to kb_points (知识点库建表：讲解/频次/典型错误/例题/关键词/模块路径/教材版本)

Revision ID: c0ffee123456
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c0ffee123456'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('kb_points', sa.Column('explanation', sa.Text(), nullable=True))
    op.add_column('kb_points', sa.Column('frequency', sa.Integer(), nullable=True, server_default='3'))
    op.add_column('kb_points', sa.Column('typical_errors', sa.String(), nullable=True))
    op.add_column('kb_points', sa.Column('example', sa.Text(), nullable=True))
    op.add_column('kb_points', sa.Column('keywords', sa.String(), nullable=True))
    op.add_column('kb_points', sa.Column('module_path', sa.String(128), nullable=True))
    op.add_column('kb_points', sa.Column('source_version', sa.String(32), nullable=True))


def downgrade() -> None:
    for col in ('explanation', 'frequency', 'typical_errors', 'example', 'keywords', 'module_path', 'source_version'):
        op.drop_column('kb_points', col)

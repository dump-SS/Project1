"""add ai_call_logs table (PRD 6.5 留痕)

Revision ID: a6b5c4d3e2f1
Revises: d5e4f3a2b7c8
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a6b5c4d3e2f1'
down_revision: Union[str, None] = 'd5e4f3a2b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_call_logs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('function_type', sa.String(32), nullable=False),
        sa.Column('data_class', sa.String(32), nullable=True),
        sa.Column('input_digest', sa.String(256), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('egress_blocked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cost_units', sa.Float(), nullable=True),
        sa.Column('error_msg', sa.String(256), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_call_logs_function_type', 'ai_call_logs', ['function_type'])
    op.create_index('ix_ai_call_logs_created_at', 'ai_call_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_call_logs_created_at', table_name='ai_call_logs')
    op.drop_index('ix_ai_call_logs_function_type', table_name='ai_call_logs')
    op.drop_table('ai_call_logs')

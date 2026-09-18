"""add community tab 三表（板块三 M2/M3）

Revision ID: cafef00d0001
Revises: f7012345abcd
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cafef00d0001'
down_revision: Union[str, None] = 'f7012345abcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'community_features',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('anon_participant_id', sa.String(64), nullable=False),
        sa.Column('salt_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('stage', sa.String(16), nullable=False),
        sa.Column('metric', sa.String(16), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('anon_participant_id', 'period', 'metric', name='uq_community_feature'),
    )
    op.create_index('ix_community_features_anon', 'community_features', ['anon_participant_id'])
    op.create_index('ix_community_features_period', 'community_features', ['period'])
    op.create_index('ix_community_features_stage_metric', 'community_features', ['stage', 'metric'])

    op.create_table(
        'community_aggregates',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('stage', sa.String(16), nullable=False),
        sa.Column('metric', sa.String(16), nullable=False),
        sa.Column('pool_size', sa.Integer(), nullable=False),
        sa.Column('percentiles', sa.Text(), nullable=False),
        sa.Column('histogram', sa.Text(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('period', 'stage', 'metric', name='uq_community_aggregate'),
    )
    op.create_index('ix_community_aggregates_period', 'community_aggregates', ['period'])
    op.create_index('ix_community_aggregates_stage_metric', 'community_aggregates', ['stage', 'metric'])

    op.create_table(
        'community_audit_logs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('event', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_community_audit_user', 'community_audit_logs', ['user_id'])
    op.create_index('ix_community_audit_created', 'community_audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('community_audit_logs')
    op.drop_table('community_aggregates')
    op.drop_table('community_features')

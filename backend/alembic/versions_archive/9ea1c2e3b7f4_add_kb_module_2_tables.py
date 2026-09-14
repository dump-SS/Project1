"""add kb module 2 tables (板块二 8 张 kb_ 表)

Revision ID: 9ea1c2e3b7f4
Revises: ee1d7e6e893c
Create Date: 2026-08-24

PRD 12.4 数据模型增量：kb_subjects / kb_points / kb_point_relations /
kb_errors / kb_error_points / kb_point_mastery / kb_review_logs / kb_embeddings。
upgrade 从基线上建这 8 张表；downgrade 删除。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9ea1c2e3b7f4'
down_revision: Union[str, None] = 'ee1d7e6e893c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kb_subjects',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('grade_band', sa.String(16), nullable=True),
        sa.Column('version', sa.String(32), nullable=False, server_default='1.0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('code', name='uq_kb_subjects_code'),
    )
    op.create_table(
        'kb_points',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('subject_code', sa.String(32), nullable=False),
        sa.Column('code', sa.String(128), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('error_tip', sa.Text(), nullable=True),
        sa.Column('parent_id', sa.String(64), nullable=True),
        sa.Column('difficulty', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('exam_weight', sa.Float(), nullable=False, server_default='0.1'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index('ix_kb_points_subject_code', 'kb_points', ['subject_code'])
    op.create_index('ix_kb_points_parent_id', 'kb_points', ['parent_id'])

    op.create_table(
        'kb_point_relations',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('src_id', sa.String(64), nullable=False),
        sa.Column('dst_id', sa.String(64), nullable=False),
        sa.Column('type', sa.String(32), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False, server_default='0.5'),
    )
    op.create_index('ix_kb_point_relations_src_id', 'kb_point_relations', ['src_id'])
    op.create_index('ix_kb_point_relations_dst_id', 'kb_point_relations', ['dst_id'])

    op.create_table(
        'kb_errors',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('subject', sa.String(32), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('student_answer', sa.Text(), nullable=True),
        sa.Column('correct_answer', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(64), nullable=True),
        sa.Column('error_note', sa.Text(), nullable=True),
        sa.Column('vector_id', sa.String(64), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_kb_errors_user_id', 'kb_errors', ['user_id'])
    op.create_index('ix_kb_errors_subject', 'kb_errors', ['subject'])

    op.create_table(
        'kb_error_points',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('error_id', sa.String(64), nullable=False),
        sa.Column('point_id', sa.String(64), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.UniqueConstraint('error_id', 'point_id', name='uq_error_point'),
    )
    op.create_index('ix_kb_error_points_error_id', 'kb_error_points', ['error_id'])
    op.create_index('ix_kb_error_points_point_id', 'kb_error_points', ['point_id'])

    op.create_table(
        'kb_point_mastery',
        sa.Column('user_id', sa.String(64), primary_key=True),
        sa.Column('point_id', sa.String(64), primary_key=True),
        sa.Column('mastery', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'point_id', name='uq_user_point'),
    )

    op.create_table(
        'kb_review_logs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('error_id', sa.String(64), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('recall_correct', sa.Boolean(), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_index('ix_kb_review_logs_error_id', 'kb_review_logs', ['error_id'])
    op.create_index('ix_kb_review_logs_user_id', 'kb_review_logs', ['user_id'])

    op.create_table(
        'kb_embeddings',
        sa.Column('vector_id', sa.String(64), primary_key=True),
        sa.Column('ref_type', sa.String(16), nullable=False),
        sa.Column('ref_id', sa.String(64), nullable=False),
        sa.Column('model', sa.String(64), nullable=False),
        sa.Column('dim', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_kb_embeddings_ref_id', 'kb_embeddings', ['ref_id'])


def downgrade() -> None:
    for table in (
        'kb_embeddings',
        'kb_review_logs',
        'kb_point_mastery',
        'kb_error_points',
        'kb_errors',
        'kb_point_relations',
        'kb_points',
        'kb_subjects',
    ):
        op.drop_table(table)

"""C 板块 M2：self_report 软字段放开为可空 + 学习记录来源字段

Revision ID: c7a1f2e4d9b3
Revises: b81d83bafb89
Create Date: 2026-09-25

**为什么改**（三处硬阻塞撞在同一堵墙上，需求单见 docs/refactor-c-handoff-to-x0.md）：

1. **D20 计时收尾三层形态**：唯一"半强制"的只有**完成度**；专注/疲劳/难度是模型从
   "一句感受"转译的**软字段**，情绪快捷词也只是"可选兜底"。四列 NOT NULL 会逼实现侧编数据。
2. **D34 口语转译兜底**：验收明确要求「转译失败**不造数**」——原约束下只能二选一：
   造数，或 400 拒绝用户提交。
3. **D49 成绩回填喂状态评估**：考试成绩是**客观结果**，它没有自评（没人会为一次期中考试
   填"专注度 4 分"）。故新增 `source` / `source_exam_id`，让考试记录可被识别与过滤，
   而不是靠编造自评混进状态窗口。

⚠️ SQLite 不支持 `ALTER COLUMN`，必须走 `batch_alter_table`（内部重建表 + 拷数据）。
   批量重建时 NOT NULL 新列必须有默认值，所以 `source` 先带 `server_default` 落值、
   再显式去掉——最终 schema 与 ORM 的 Python 侧 default 保持一致（否则 `alembic check` 会报差异）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7a1f2e4d9b3'
down_revision: Union[str, None] = 'b81d83bafb89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('learning_records', schema=None) as batch_op:
        # 1) 自评四列放开为可空（软字段缺失 = 正常路径，不是脏数据）
        batch_op.alter_column('self_report_focus', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('self_report_fatigue', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('self_report_emotion', existing_type=sa.String(length=16), nullable=True)
        batch_op.alter_column('self_report_difficulty_feel', existing_type=sa.String(length=16), nullable=True)

        # 2) 记录来源（D49）：先带默认值落值，再摘掉 server_default
        batch_op.add_column(
            sa.Column('source', sa.String(length=16), nullable=False, server_default='self_report')
        )
        batch_op.alter_column('source', server_default=None)
        batch_op.add_column(sa.Column('source_exam_id', sa.String(length=64), nullable=True))
        batch_op.create_index(
            op.f('ix_learning_records_source'), ['source'], unique=False
        )
        batch_op.create_index(
            op.f('ix_learning_records_source_exam_id'), ['source_exam_id'], unique=False
        )

    # 3) 考试时长（可空）：成绩回填要生成学习记录，而记录时长必填——
    #    考试时长是客观事实，填了才生成记录，不填就不生成。
    with op.batch_alter_table('exams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duration_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('exams', schema=None) as batch_op:
        batch_op.drop_column('duration_minutes')

    with op.batch_alter_table('learning_records', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_learning_records_source_exam_id'))
        batch_op.drop_index(op.f('ix_learning_records_source'))
        batch_op.drop_column('source_exam_id')
        batch_op.drop_column('source')
        # 回退成 NOT NULL 前必须先清掉空值，否则 SQLite 重建表会失败
        batch_op.execute(
            "UPDATE learning_records SET "
            "self_report_focus = COALESCE(self_report_focus, 3), "
            "self_report_fatigue = COALESCE(self_report_fatigue, 3), "
            "self_report_emotion = COALESCE(self_report_emotion, 'neutral'), "
            "self_report_difficulty_feel = COALESCE(self_report_difficulty_feel, 'moderate')"
        )
        batch_op.alter_column('self_report_focus', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('self_report_fatigue', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('self_report_emotion', existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column('self_report_difficulty_feel', existing_type=sa.String(length=16), nullable=False)

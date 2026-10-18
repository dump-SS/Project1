"""add chat_jobs（带图 Chat 异步任务，契约 v1.13.0）

Revision ID: b8e2d4f1a7c3
Revises: 4c0b1c004f69
Create Date: 2026-10-18 17:05:00.000000

为什么需要这一格
----------------
带图 Chat 改成异步（`POST /chat/media` 入队 + `GET /chat/jobs/{jobId}` 轮询）
需要一处**跨请求可查**的任务状态。不能用内存：进程内队列在实例重启时会连同
未完成任务一起消失，而 brief 要求「实例重启，队列里还有 job」有确定行为
（启动对账把残留置 failed）。所以状态必须落库。

为什么它是低风险的
------------------
- **纯新建表**，不碰任何既有表 → 没有 ALTER 语义差异、没有存量行 NOT NULL 违例；
- 不涉及 `batch_alter_table`（SQLite 的建临时表重建路径），
  因此不会踩 `AGENTS.md` §四·六 那个「同一个 batch 里 add NOT NULL 默认值
  再摘默认值导致存量行拿到 NULL」的坑（空表时 INSERT 插 0 行，本就不触发）；
- BOOLEAN 列 `crisis` 的默认值用 **`sa.false()`** 而不是 `sa.text('0')`：
  PG 会对整数字面量默认值报 `DatatypeMismatch`（2026-10-01 事故，见 AGENTS.md §四·六）。
  `false()` 由方言各自编译：SQLite 出 0、PG 出 false；
- 索引与模型声明一致（`ix_chat_jobs_user_id` 单列 + `ix_chat_jobs_user_status` 复合），
  所以 `alembic check` 不会报漂移。

三向复验（AGENTS.md §四·六）
---------------------------
- 空库 SQLite：upgrade head 通过，且表/索引/列都在
- 非空库 SQLite：先跑到 4c0b1c004f69 造 chat 相关存量数据，再 upgrade，
  确认 chat_jobs 建出来且既有表数据未受影响
- Postgres：在 Neon 分支上真跑 upgrade（不是生产库），确认
  BOOLEAN 默认值在 PG 上编译成 false 而不是 0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e2d4f1a7c3'
down_revision: Union[str, None] = '4c0b1c004f69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='queued', nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('media_key', sa.String(length=512), nullable=False),
        sa.Column('reply', sa.Text(), nullable=True),
        sa.Column('intent', sa.String(length=32), nullable=True),
        # ⚠️ sa.false()：PG 上整数默认值会 DatatypeMismatch，必须让方言编译
        sa.Column('crisis', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('cards_json', sa.Text(), nullable=True),
        sa.Column('session_id', sa.String(length=64), nullable=True),
        sa.Column('context_stack_json', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_jobs_created_at', 'chat_jobs', ['created_at'], unique=False)
    op.create_index('ix_chat_jobs_user_id', 'chat_jobs', ['user_id'], unique=False)
    op.create_index('ix_chat_jobs_user_status', 'chat_jobs', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chat_jobs_user_status', table_name='chat_jobs')
    op.drop_index('ix_chat_jobs_user_id', table_name='chat_jobs')
    op.drop_index('ix_chat_jobs_created_at', table_name='chat_jobs')
    op.drop_table('chat_jobs')

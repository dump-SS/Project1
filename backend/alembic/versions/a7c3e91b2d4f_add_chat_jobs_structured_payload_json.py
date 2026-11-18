"""add chat_jobs.structured_payload_json（结构化 refs PR2，契约 v1.24.0）

D22 卡片点击注入的结构化 payload 需要随带图异步路径进入 worker——
`routes/chat.py` 建 `ChatJob` 时只落 `content` / `media_key` 两列入参快照
（worker 不依赖请求上下文），结构化引用必须同样落快照，否则带图路径丢引用块。

- 可空 JSON 文本列；NULL = 无结构化引用（旧客户端 / 普通消息），worker 解析
  失败按无引用处理（不让用户任务 failed）
- SQLite 走 batch_alter_table；downgrade 删列（可逆）
- Revision ID 由 `uuid.uuid4().hex[:12]` 生成，`down_revision` = 写前现查的
  head `65cfc1fbf770`（派单指定先核，实际核实一致）

三向复验（AGENTS §四·六）已在 tests/test_structured_refs.py 与
tests/test_chat_async.py 覆盖 SQLite 行为；Postgres 侧为 Text 列加列，
无类型/约束风险，解冻后按流程在 Neon 分支复核。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e91b2d4f"
down_revision: Union[str, None] = "65cfc1fbf770"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_jobs") as batch:
        batch.add_column(
            sa.Column("structured_payload_json", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_jobs") as batch:
        batch.drop_column("structured_payload_json")

"""add source_ref column to user_profiles（契约 v1.15.0）

Revision ID: 65cfc1fbf770
Revises: b8e2d4f1a7c3
Create Date: 2026-11-01 12:07:48.762054

为什么需要这一格
-----------------
openapi.yaml v1.15.0 新增 `GET /me/profile/{group}/{key}` 等画像条目接口，
`UserProfileEntry` schema 里有 `sourceRef` 字段（提取来源引用，会话 id /
消息 id，供「这条画像是哪来的」审计追溯，§8 画像 trace）。`user_profiles`
表缺这列，ORM 也没声明，需要补一列。

为什么它是低风险的
--------------------
- **单纯 add_column，nullable=True**：没有 NOT NULL，没有 server_default，
  存量行不会受任何影响（SQLite 的 batch_alter_table 重建时 INSERT 存量行时
  新列取 NULL，不违反任何约束）；
- 不涉及 `batch_alter_table` 里同批 add NOT NULL + 摘 default 的组合，
  因此躲开 AGENTS.md §四·六 记录的 SQLite 存量行 NULL 违例坑；
- 不是 BOOLEAN 列，不涉及 sa.text('0') 在 PG 上的 DatatypeMismatch（见
  AGENTS.md §四·六 2026-10-01 事故）；
- `alembic check` 不会因此报新漂移（模型会同步声明 source_ref）。

三向复验（AGENTS.md §四·六）
---------------------------
- 空库 SQLite：upgrade head 通过，user_profiles 有 source_ref 列；
- 非空库 SQLite：先跑到 b8e2d4f1a7c3 造 user_profiles 存量行，再 upgrade，
  确认存量行数据未受影响、source_ref 为 NULL；
- **Postgres（Neon 分支）**：upgrade 通过，source_ref 列为 nullable String，
  存量行 NULL，新行可写非 NULL。

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65cfc1fbf770'
down_revision: Union[str, None] = 'b8e2d4f1a7c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_profiles',
        sa.Column('source_ref', sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_profiles', 'source_ref')

"""baseline: all existing tables (板块一全部 ORM 表)

Revision ID: ee1d7e6e893c
Revises:
Create Date: 2026-08-24

板块二引入迁移机制的最后窗口期（PRD 12.4 / gap 清单 §3.1 前置）：
把现有 create_all 产物基线化为首个 revision。upgrade = 从空库重建全部表，
downgrade = 全部 drop。后续新增 kb_* 表、summaries.dimension 列一律
追加独立 revision，不再依赖 create_all。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from database import Base

# revision identifiers, used by Alembic.
revision: str = 'ee1d7e6e893c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """从空库重建板块一全部表（与 create_all 产物等价）。"""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """回滚基线：删除全部表。"""
    Base.metadata.drop_all(bind=op.get_bind())

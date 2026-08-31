"""merge community migration heads (板块三 M1/M2 两分支合并)

Revision ID: a7b8c9d0e1f2
Revises: cafef00d0001, bead00000001
Create Date: 2026-08-31

两个板块三迁移分支在 f7012345abcd 之后分叉：
- cafef00d0001（community_features / community_aggregates / community_audit_logs 三表）
- bead00000001（settings.community_consent_enabled / community_auto_participate 两列）
二者互不依赖，本迁移仅做分支合并，upgrade/downgrade 均为空。
"""
from typing import Sequence, Union

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = ('cafef00d0001', 'bead00000001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

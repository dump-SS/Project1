"""
AssessmentSnapshot：状态评估快照

对应 openapi.yaml：
  - AssessmentSnapshot（嵌入 LearningRecordCreated / LearningRecordDeleted 响应）
  - 提交/删除学习记录时同步重算，落库作为派生记录

说明：
  - 「状态分是记录的派生资源」——不提供 POST 手动计算接口，避免前端伪造触发。
  - windowScore / trend / stateLabel 不暴露权重与公式（PRD 6.1 / 8.3）。
  - 不为 AssessmentSnapshot 单独建基表，必要时用视图 / 物化视图承载 StateResult 列表（下一步加）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AssessmentSnapshot(Base):
    """每次提交/删除学习记录时同步重算并落库，作为派生记录。"""

    __tablename__ = "assessment_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    subject: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    window_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-1
    trend: Mapped[str] = mapped_column(String(8), nullable=False)  # up/flat/down
    state_label: Mapped[str] = mapped_column(String(32), nullable=False)
    data_sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    # 可解释性依据（PRD 8.3），不暴露权重与公式
    based_on_record_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)  # JSON 列表字符串
    based_on_signals: Mapped[str | None] = mapped_column(String(512), nullable=True)  # JSON 列表字符串

    # 关联的 learning record（如有），删除记录时可追溯
    trigger_record_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("learning_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # 用户反馈：该状态判断是否准确（PRD 9 节指标，AI 调权迭代用）
    # null=未反馈，true/false=已反馈，PUT 幂等覆盖
    feedback_accurate: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    feedback_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

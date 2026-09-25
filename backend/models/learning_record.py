"""
LearningRecord：学习记录

对应 openapi.yaml：
  - POST   /learning-records                       → RecordInput（创建时同步重算 assessment + 创建 recommendation）
  - GET    /learning-records                       → LearningRecordList
  - DELETE /learning-records/{recordId}            → 删除并触发重算

behavior / selfReport 字段比较多，按 schema 平铺成列（不嵌 JSON），便于 SQL 聚合查询；
note 是可选 ≤100 字备注，单独成列。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    subject: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-600

    plan_task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("plan_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # behavior 行为数据
    behavior_completion: Mapped[str] = mapped_column(String(16), nullable=False)  # completed/partial/abandoned
    behavior_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1
    behavior_interruptions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    behavior_blur_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None=未采集，0=采集到0次

    # selfReport 自评数据
    # ⚠️ 四列**全部可空**（2026-09-25 放开，原为 NOT NULL）——依据目标态 §3.7(a)：
    # 三层收尾里唯一"半强制"的只有**完成度**；专注/疲劳/难度是模型从"一句感受"转译的
    # **软字段**，情绪快捷词也只是"可选兜底"。转译不出就缺省（D34：宁缺毋滥、不造数）。
    # 原来强制 NOT NULL 会逼实现侧编数据，正是 D34 要禁止的。
    # 自评整段缺失的典型场景：考试成绩回填生成的记录（source=exam）——考试没有自评。
    self_report_focus: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    self_report_fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    self_report_emotion: Mapped[str | None] = mapped_column(String(16), nullable=True)  # positive/neutral/negative
    self_report_difficulty_feel: Mapped[str | None] = mapped_column(String(16), nullable=True)  # easy/moderate/hard

    # 记录来源（D49）：自评记录 / 考试成绩回填。默认 self_report。
    # 为什么要这一列：考试是**客观结果**，它没有自评，不能靠编造自评混进状态窗口；
    # 有了来源，消费方（状态评估 / mastery / 画像 / 列表）才能区分与过滤。
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="self_report", index=True)
    source_exam_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # ≤100 字
    skip_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

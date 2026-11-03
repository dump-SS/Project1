"""
学习计划（openapi.yaml 3.x）

PlanTask / PlanTaskDetail / PlanTaskUpdate / PlanAdaptation / Plan / PlanCreate / PlanList
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination
from .enums import StateLabel, Subject, TaskStatus


class PlanTask(BaseModel):
    """计划内的单个任务。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "taskId": "t_30011",
                "subject": "SX",
                "topic": "函数图像与性质 · 巩固已学",
                "estimatedMinutes": 40,
                "priority": 1,
                "status": "pending",
                "goalId": "g_5501",
            }
        },
    )

    task_id: str = Field(..., alias="taskId")
    subject: Subject
    topic: str = Field(..., description="内容方向，颗粒度到「学科 + 方向」")
    estimated_minutes: int = Field(..., alias="estimatedMinutes", description="预计时长（分钟）")
    priority: int = Field(..., description="数字越小越靠前")
    status: TaskStatus
    goal_id: str | None = Field(None, alias="goalId", description="无关联时为 null")


class PlanTaskDetail(PlanTask):
    """任务调整后的返回结构。"""

    model_config = ConfigDict(populate_by_name=True)

    removed: bool = Field(..., description="软删除标记")
    user_adjusted: bool = Field(..., alias="userAdjusted", description="是否被用户手动调整过（算法反馈信号）")
    updated_at: datetime = Field(..., alias="updatedAt")


class PlanTaskUpdate(BaseModel):
    """调整任务请求体，至少传一项。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"estimatedMinutes": 30, "status": "partial"}},
    )

    estimated_minutes: int | None = Field(None, alias="estimatedMinutes", ge=10, le=600)
    status: TaskStatus | None = None
    removed: bool | None = Field(None, description="true 表示删除该任务（软删除）")


class PlanAdaptation(BaseModel):
    """本次计划基于哪次状态评估做了强度调整。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "assessmentId": "a_7742",
                "stateLabel": "fatigue_warning",
                "adjustment": "reduce_load",
                "note": "最近状态偏疲劳，本次总时长下调，单任务时长缩短并增加间隔",
            }
        },
    )

    assessment_id: str = Field(..., alias="assessmentId")
    state_label: StateLabel = Field(..., alias="stateLabel")
    adjustment: str = Field(..., description="调整方向，如 reduce_load")
    note: str = Field(..., description="面向用户的调整说明")


class PlanWeaknessHint(BaseModel):
    """板块二短板提示（v2.3 增量）。"""

    model_config = ConfigDict(populate_by_name=True)

    point_id: str = Field(..., alias="pointId")
    point_name: str = Field(..., alias="pointName")
    mastery: float = Field(..., description="0-1，样本充足且 <0.7 才出现")
    subject_code: str | None = Field(None, alias="subjectCode")


class Plan(BaseModel):
    """学习计划。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "planId": "p_9001",
                "planDate": "2026-08-16",
                "availableMinutes": 120,
                "adaptedFrom": {
                    "assessmentId": "a_7742",
                    "stateLabel": "fatigue_warning",
                    "adjustment": "reduce_load",
                    "note": "最近状态偏疲劳，本次总时长下调",
                },
                "tasks": [
                    {
                        "taskId": "t_30011",
                        "subject": "SX",
                        "topic": "函数图像与性质 · 巩固已学",
                        "estimatedMinutes": 40,
                        "priority": 1,
                        "status": "pending",
                        "goalId": "g_5501",
                    }
                ],
                "createdAt": "2026-08-16T18:00:00+08:00",
            }
        },
    )

    plan_id: str = Field(..., alias="planId")
    plan_date: date = Field(..., alias="planDate")
    available_minutes: int = Field(..., alias="availableMinutes")
    adapted_from: PlanAdaptation | None = Field(
        None, alias="adaptedFrom", description="新用户无历史数据时为 null"
    )
    tasks: list[PlanTask]
    weakness_hints: list[PlanWeaknessHint] = Field(
        default_factory=list, alias="weaknessHints", description="板块二短板提示；新用户为空"
    )
    created_at: datetime = Field(..., alias="createdAt")


class PlanTaskInput(BaseModel):
    """显式任务输入（v1.15.0）：作业单确认卡路径，与 WorksheetItem 同构但归 C 板块所有。

    为什么不直接复用 schemas/worksheet.WorksheetItem：那是 F 板块抽取响应的形状，
    C 的计划创建不该 import F 的 schema（板块边界）；字段口径以契约为准保持一致，
    漂移由 openapi.yaml 单一真源约束。
    """

    model_config = ConfigDict(populate_by_name=True)

    subject: Subject = Field(..., description="学科代码")
    topic: str = Field(..., min_length=1, max_length=100, description="作业内容")
    estimated_minutes: int = Field(..., alias="estimatedMinutes", ge=5, le=240, description="预计时长（分钟）")


class PlanCreate(BaseModel):
    """生成计划请求体。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "planDate": "2026-08-16",
                "availableMinutes": 120,
                "goalIds": ["g_5501"],
            }
        },
    )

    plan_date: date = Field(..., alias="planDate")
    available_minutes: int = Field(..., alias="availableMinutes", ge=10, le=600)
    goal_ids: list[str] | None = Field(None, alias="goalIds", description="不传则使用全部 active 目标")
    regenerate: bool | None = Field(None, description="true 覆盖当日已有计划")
    tasks: list[PlanTaskInput] | None = Field(
        None,
        alias="tasks",
        min_length=1,
        max_length=20,
        description=(
            "可选（v1.15.0）：显式任务列表（作业单确认卡路径）。非空时跳过规则引擎——"
            "不查目标、不做疲劳降载，adaptedFrom 为 null，priority 按顺序 1..n。"
            "与 goalIds 互斥：同时传时 goalIds 被忽略。不传时行为与 v1.14.0 一致。"
        ),
    )


class PlanList(BaseModel):
    items: list[Plan]
    pagination: Pagination

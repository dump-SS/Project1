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
                "subject": "math",
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
    user_adjusted: bool = Field(..., description="是否被用户手动调整过（算法反馈信号）")
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
                        "subject": "math",
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
    created_at: datetime = Field(..., alias="createdAt")


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


class PlanList(BaseModel):
    items: list[Plan]
    pagination: Pagination

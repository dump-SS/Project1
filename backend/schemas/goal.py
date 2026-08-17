"""
学习目标（openapi.yaml 2.x）

GoalProgress / Goal / GoalSummary / GoalCreate / GoalUpdate / GoalList
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination
from .enums import GoalType, Subject


class GoalProgress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    planned_tasks: int = Field(..., alias="plannedTasks", description="已规划任务数")
    completed_tasks: int = Field(..., alias="completedTasks", description="已完成任务数")
    ratio: float = Field(..., alias="ratio", ge=0.0, le=1.0, description="完成比例")


class GoalBase(BaseModel):
    """Goal 与 GoalSummary 共享字段。"""

    goal_id: str = Field(..., alias="goalId")
    type: GoalType
    subject: Subject
    title: str = Field(..., max_length=50, description='≤50 字，如「两周后期中考试数学 120+」')


class GoalSummary(GoalBase):
    """列表中的目标条目。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "goalId": "g_5501",
                "type": "short_term",
                "subject": "math",
                "title": "两周后期中考试数学 120+",
                "targetDate": "2026-08-30",
                "status": "active",
                "progress": {"plannedTasks": 12, "completedTasks": 7, "ratio": 0.58},
            }
        },
    )

    target_date: date | None = Field(None, alias="targetDate")
    status: str = Field(..., description="active / archived")
    progress: GoalProgress


class Goal(GoalSummary):
    """单个目标完整对象（响应中比 Summary 多 description / createdAt）。"""

    description: str | None = Field(None, max_length=200)
    created_at: datetime = Field(..., alias="createdAt")


class GoalCreate(BaseModel):
    """创建目标请求体。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "type": "short_term",
                "subject": "math",
                "title": "两周后期中考试数学 120+",
                "description": "函数和数列这两章不太熟，想重点补",
                "targetDate": "2026-08-30",
            }
        },
    )

    type: GoalType
    subject: Subject = Field(..., description="所属学科，跨学科目标填 other")
    title: str = Field(..., max_length=50)
    description: str | None = Field(None, max_length=200, description="≤200 字自由文本")
    target_date: date | None = Field(None, alias="targetDate", description="短期目标建议必填")
    template_id: str | None = Field(None, alias="templateId", description="从预设模板创建时带上")


class GoalUpdate(BaseModel):
    """更新 / 归档目标请求体，字段全可选。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"targetDate": "2026-09-05", "status": "active"}},
    )

    title: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=200)
    target_date: date | None = Field(None, alias="targetDate")
    status: str | None = Field(None, description="active / archived（归档代替删除）")


class GoalList(BaseModel):
    items: list[GoalSummary]
    pagination: Pagination

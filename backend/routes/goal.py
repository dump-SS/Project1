"""/goals 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import GOAL_LIST_MOCK
from schemas.common import Pagination
from schemas.goal import Goal, GoalCreate, GoalList, GoalUpdate
from .deps import current_user
from schemas.user import User

router = APIRouter(prefix="/goals", tags=["学习目标"])


@router.post("", response_model=Goal, status_code=status.HTTP_201_CREATED, summary="创建学习目标 ①")
def create_goal(body: GoalCreate, _user: User = Depends(current_user)) -> Goal:
    return Goal.model_validate(
        {
            "goalId": "g_5501",
            "type": body.type,
            "subject": body.subject,
            "title": body.title,
            "description": body.description,
            "targetDate": body.target_date.isoformat() if body.target_date else None,
            "status": "active",
            "progress": {"plannedTasks": 0, "completedTasks": 0, "ratio": 0},
            "createdAt": "2026-08-16T09:20:00+08:00",
        }
    )


@router.get("", response_model=GoalList, summary="目标列表（含进度）")
def list_goals(
    status: str = "active",
    subject: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _user: User = Depends(current_user),
) -> GoalList:
    return GOAL_LIST_MOCK


@router.patch("/{goal_id}", response_model=Goal, summary="更新 / 归档目标")
def update_goal(
    goal_id: str,
    body: GoalUpdate,
    _user: User = Depends(current_user),
) -> Goal:
    return Goal.model_validate(
        {
            "goalId": goal_id,
            "type": "short_term",
            "subject": "math",
            "title": "两周后期中考试数学 120+",
            "description": "函数和数列这两章不太熟，想重点补",
            "targetDate": "2026-09-05",
            "status": "active",
            "progress": {"plannedTasks": 12, "completedTasks": 7, "ratio": 0.58},
            "createdAt": "2026-08-16T09:20:00+08:00",
        }
    )

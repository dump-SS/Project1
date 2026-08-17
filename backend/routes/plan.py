"""/plans 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import PLAN_LIST_MOCK
from schemas.plan import Plan, PlanCreate, PlanList, PlanTaskDetail, PlanTaskUpdate
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/plans", tags=["学习计划"])


@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED, summary="生成学习计划 ②")
def create_plan(body: PlanCreate, _user: User = Depends(current_user)) -> Plan:
    # mock：直接返回示例计划
    return PLAN_LIST_MOCK.items[0]


@router.get("", response_model=PlanList, summary="计划列表")
def list_plans(
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _user: User = Depends(current_user),
) -> PlanList:
    return PLAN_LIST_MOCK


@router.get("/{plan_id}", response_model=Plan, summary="计划详情")
def get_plan(plan_id: str, _user: User = Depends(current_user)) -> Plan:
    return PLAN_LIST_MOCK.items[0]


@router.patch(
    "/{plan_id}/tasks/{task_id}",
    response_model=PlanTaskDetail,
    summary="调整任务 / 确认完成情况",
)
def update_plan_task(
    plan_id: str,
    task_id: str,
    body: PlanTaskUpdate,
    _user: User = Depends(current_user),
) -> PlanTaskDetail:
    # status 可选（契约 PlanTaskUpdate 全部可选）；body.status 为 None 时退化为 partial。
    # body.status 是 TaskStatus 枚举时 .value；字符串时直接用。避免 (None or "partial").value AttributeError。
    status_value = body.status.value if body.status is not None else "partial"
    return PlanTaskDetail.model_validate(
        {
            "taskId": task_id,
            "subject": "math",
            "topic": "函数图像与性质 · 巩固已学",
            "estimatedMinutes": body.estimated_minutes or 30,
            "priority": 1,
            "status": status_value,
            "goalId": "g_5501",
            "removed": body.removed or False,
            "userAdjusted": True,
            "updatedAt": "2026-08-16T21:05:00+08:00",
        }
    )

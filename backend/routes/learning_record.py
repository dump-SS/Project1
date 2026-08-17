"""/learning-records 系列。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from mock_data import LEARNING_RECORD_LIST_MOCK
from schemas.learning_record import (
    LearningRecord,
    LearningRecordCreated,
    LearningRecordDeleted,
    LearningRecordList,
    RecordInput,
)
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/learning-records", tags=["学习记录"])


@router.post(
    "",
    response_model=LearningRecordCreated,
    status_code=status.HTTP_201_CREATED,
    summary="提交学习记录（核心接口）③④",
)
def create_learning_record(
    body: RecordInput, _user: User = Depends(current_user)
) -> LearningRecordCreated:
    # mock：返回同步重算 + 建议句柄
    return LearningRecordCreated.model_validate(
        {
            "recordId": "r_88012",
            "subject": body.subject,
            "startedAt": body.started_at.isoformat(),
            "durationMinutes": body.duration_minutes,
            "planTaskId": body.plan_task_id,
            "behavior": {
                "completion": body.behavior.completion,
                "accuracy": body.behavior.accuracy,
                "interruptions": body.behavior.interruptions or 0,
                "blurCount": body.behavior.blur_count or 0,
            },
            "selfReport": {
                "focus": body.self_report.focus,
                "fatigue": body.self_report.fatigue,
                "emotion": body.self_report.emotion,
                "difficultyFeel": body.self_report.difficulty_feel,
            },
            "assessment": {
                "assessmentId": "a_7742",
                "subject": body.subject,
                "windowScore": 0.48,
                "trend": "down",
                "stateLabel": "fatigue_warning",
                "dataSufficient": True,
                "recordCount": 7,
            },
            "recommendation": {"recommendationId": "rec_20301", "status": "pending"},
            "createdAt": "2026-08-16T19:46:00+08:00",
        }
    )


@router.get("", response_model=LearningRecordList, summary="学习记录列表")
def list_learning_records(
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _user: User = Depends(current_user),
) -> LearningRecordList:
    return LEARNING_RECORD_LIST_MOCK


@router.delete(
    "/{record_id}",
    response_model=LearningRecordDeleted,
    summary="删除学习记录并重算当前窗口",
)
def delete_learning_record(
    record_id: str, _user: User = Depends(current_user)
) -> LearningRecordDeleted:
    return LearningRecordDeleted.model_validate(
        {
            "deleted": True,
            "recordId": record_id,
            "recalculatedAssessment": {
                "assessmentId": "a_7751",
                "subject": "math",
                "windowScore": 0.53,
                "trend": "flat",
                "stateLabel": "insufficient_data",
                "dataSufficient": False,
                "recordCount": 2,
            },
        }
    )

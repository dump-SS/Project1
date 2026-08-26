"""
学习记录（openapi.yaml 4.x）

RecordBehavior / RecordSelfReport / RecordInput / LearningRecord /
AssessmentSnapshot / LearningRecordCreated / LearningRecordList / LearningRecordDeleted
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination
from .enums import Completion, DifficultyFeel, Emotion, Subject


class RecordBehavior(BaseModel):
    """行为数据（系统自动记录为主）。"""

    model_config = ConfigDict(populate_by_name=True)

    completion: Completion
    accuracy: float | None = Field(None, ge=0.0, le=1.0, description="正确率 0-1；无客观测验时不传")
    interruptions: int = Field(default=0, ge=0, description="中断次数，默认 0")
    blur_count: int | None = Field(None, ge=0, alias="blurCount", description="页面失焦次数（小程序弱信号）")


class RecordSelfReport(BaseModel):
    """自评数据，控制在 10 秒内完成。"""

    focus: int = Field(..., ge=1, le=5, description="专注度 1-5")
    fatigue: int = Field(..., ge=1, le=5, description="疲劳度 1-5")
    emotion: Emotion
    difficulty_feel: DifficultyFeel = Field(..., alias="difficultyFeel")


class RecordInput(BaseModel):
    """提交学习记录请求体。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "subject": "SX",
                "startedAt": "2026-08-16T19:00:00+08:00",
                "durationMinutes": 45,
                "planTaskId": "t_30011",
                "behavior": {"completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5},
                "selfReport": {"focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard"},
                "note": "函数图像那块看不太进去",
            }
        },
    )

    subject: Subject = Field(..., description="状态按学科分开评估，故必填")
    started_at: datetime = Field(..., alias="startedAt")
    duration_minutes: int = Field(..., alias="durationMinutes", ge=1, le=600)
    plan_task_id: str | None = Field(
        None, alias="planTaskId", description="关联计划任务；自由学习可不传"
    )
    behavior: RecordBehavior
    self_report: RecordSelfReport = Field(..., alias="selfReport")
    note: str | None = Field(None, max_length=100, description="≤100 字备注，出域受 sendTextToAI 控制")
    skip_recommendation: bool | None = Field(
        None, alias="skipRecommendation", description="true 时不自动生成建议"
    )


class LearningRecord(BaseModel):
    """已保存的学习记录。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "recordId": "r_88012",
                "subject": "SX",
                "startedAt": "2026-08-16T19:00:00+08:00",
                "durationMinutes": 45,
                "planTaskId": "t_30011",
                "behavior": {"completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5},
                "selfReport": {"focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard"},
                "createdAt": "2026-08-16T19:46:00+08:00",
            }
        },
    )

    record_id: str = Field(..., alias="recordId")
    subject: Subject
    started_at: datetime = Field(..., alias="startedAt")
    duration_minutes: int = Field(..., alias="durationMinutes")
    plan_task_id: str | None = Field(None, alias="planTaskId")
    behavior: RecordBehavior
    self_report: RecordSelfReport = Field(..., alias="selfReport")
    created_at: datetime = Field(..., alias="createdAt")


class AssessmentSnapshot(BaseModel):
    """提交/删除记录后同步重算得到的状态快照。
    v1.1 修订：assessmentId 可空、windowScore/trend 数据不足时不返回，
    与 GET /assessments/current 的 StateResult 语义一致。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "assessmentId": "a_7742",
                "subject": "SX",
                "windowScore": 0.48,
                "trend": "down",
                "stateLabel": "fatigue_warning",
                "dataSufficient": True,
                "recordCount": 7,
            }
        },
    )

    assessment_id: str | None = Field(None, alias="assessmentId", description="数据不足时为 null")
    subject: Subject
    window_score: float | None = Field(None, alias="windowScore", description="数据不足时不返回")
    trend: str | None = Field(None, description="数据不足时不返回")
    state_label: str = Field(..., alias="stateLabel")
    data_sufficient: bool = Field(..., alias="dataSufficient")
    record_count: int = Field(..., alias="recordCount")


class LearningRecordCreatedAssessment(AssessmentSnapshot):
    """LearningRecordCreated 嵌套的 assessment 字段（与 AssessmentSnapshot 同构）。"""

    pass


class LearningRecordCreatedRecommendation(BaseModel):
    """LearningRecordCreated 嵌套的 recommendation 句柄。"""

    model_config = ConfigDict(populate_by_name=True)

    recommendation_id: str = Field(..., alias="recommendationId")
    status: str  # pending / ready / failed


class LearningRecordCreated(LearningRecord):
    """提交学习记录后的响应（含同步重算的状态 + 建议句柄）。"""

    model_config = ConfigDict(populate_by_name=True)

    assessment: LearningRecordCreatedAssessment
    recommendation: LearningRecordCreatedRecommendation | None = None


class LearningRecordList(BaseModel):
    items: list[LearningRecord]
    pagination: Pagination


class LearningRecordDeleted(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "deleted": True,
                "recordId": "r_88012",
                "recalculatedAssessment": {
                    "assessmentId": "a_7751",
                    "subject": "SX",
                    "windowScore": 0.53,
                    "trend": "flat",
                    "stateLabel": "insufficient_data",
                    "dataSufficient": False,
                    "recordCount": 2,
                },
            }
        },
    )

    deleted: bool
    record_id: str = Field(..., alias="recordId")
    recalculated_assessment: LearningRecordCreatedAssessment = Field(
        ..., alias="recalculatedAssessment"
    )

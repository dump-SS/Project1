"""
学习记录（openapi.yaml 4.x）

RecordBehavior / RecordSelfReport / RecordInput / LearningRecord /
AssessmentSnapshot / LearningRecordCreated / LearningRecordList / LearningRecordDeleted
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination
from .enums import Completion, DifficultyFeel, Emotion, RecordSource, Subject


class RecordBehavior(BaseModel):
    """行为数据（系统自动记录为主）。"""

    model_config = ConfigDict(populate_by_name=True)

    completion: Completion
    accuracy: float | None = Field(None, ge=0.0, le=1.0, description="正确率 0-1；无客观测验时不传")
    interruptions: int = Field(default=0, ge=0, description="中断次数，默认 0")
    blur_count: int | None = Field(None, ge=0, alias="blurCount", description="页面失焦次数（小程序弱信号）")


class RecordSelfReport(BaseModel):
    """自评数据。

    ⚠️ 四字段**全部可空**（2026-09-25 放开，原为全必填）。依据目标态 §3.7(a)：
    三层收尾里唯一"半强制"的只有**完成度**；专注/疲劳/难度是模型从"一句感受"转译的
    **软字段**，情绪快捷词也只是"可选兜底"。转译不出就留空——状态引擎会跳过该项并按
    可用部分归一化（D34：宁缺毋滥、**不造数**）。
    整段缺失的典型场景：考试成绩回填生成的记录（考试没有自评）。
    """

    model_config = ConfigDict(populate_by_name=True)

    focus: int | None = Field(None, ge=1, le=5, description="专注度 1-5；未采集为 null")
    fatigue: int | None = Field(None, ge=1, le=5, description="疲劳度 1-5；未采集为 null")
    emotion: Emotion | None = Field(None, description="情绪；未采集为 null")
    difficulty_feel: DifficultyFeel | None = Field(
        None, alias="difficultyFeel", description="难度感受；未采集为 null"
    )


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
    self_report: RecordSelfReport | None = Field(
        None,
        alias="selfReport",
        description="自评；可整段省略（三层收尾里只有完成度是半强制的），软字段也可缺",
    )
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
    # ⚠️ 补漏（C 板块）：契约 LearningRecord 一直有 note（描述里写明「此前 RecordInput 有 note
    # 入参但出参缺失，用户无法找回自己写过的内容，已补齐」），但本 Pydantic 模型漏了该字段，
    # 于是路由明明塞了 note 也被 model_validate 静默丢弃——用户写的备注永远读不回来。
    note: str | None = Field(None, max_length=100, description="用户备注，未填写时为 null")
    created_at: datetime = Field(..., alias="createdAt")
    source: RecordSource = Field(
        RecordSource.self_report,
        description="记录来源（D49）：self_report=用户自评产生；exam=考试成绩回填自动生成（自评整段缺失）",
    )
    source_exam_id: str | None = Field(
        None, alias="sourceExamId", description="来源考试 ID；仅 source=exam 时有值"
    )


class RecordUpdate(BaseModel):
    """事后回写请求体（D15：记录是活实体，正确率/完成度/备注可事后补）。

    语义：**只在字段被显式传入时才改**（路由侧用 `model_fields_set` 判定）——
    传 `accuracy: null` 表示「清空（确实没填）」，不传表示「别动」。
    两者必须区分，否则用户只想改个备注会把正确率抹掉。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"accuracy": 0.75, "note": "老师讲完才知道对了几道"}},
    )

    completion: Completion | None = Field(None, description="修正完成度（completed / partial / abandoned）")
    accuracy: float | None = Field(
        None, ge=0.0, le=1.0, description="正确率 0-1；显式传 null 表示清空（三态中的「永不填」）"
    )
    note: str | None = Field(None, max_length=100, description="备注，≤100 字")
    self_report: RecordSelfReport | None = Field(
        None, alias="selfReport", description="整体覆盖自评四字段（不支持局部改）"
    )


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


class LearningRecordUpdated(BaseModel):
    """事后回写的响应（D15）。

    带上 `recalculatedAssessment`：回写正确率/自评会改变状态分，
    前端要能立刻拿到新读数，而不是再发一次 GET /assessments/current。
    ⚠️ 与提交记录的区别：这里**不返回 recommendation**——回写不重复触发建议生成。
    """

    model_config = ConfigDict(populate_by_name=True)

    record: LearningRecord
    recalculated_assessment: LearningRecordCreatedAssessment = Field(
        ..., alias="recalculatedAssessment"
    )

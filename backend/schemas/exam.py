"""考试（openapi.yaml `/exams` 系列）

Exam / ExamCreate / ExamUpdate / ExamList / ExamDeleted

字段名与枚举取值以 docs/openapi.yaml 为准（D49 已在 M0 冻结 schema，本模块只是把 path 挂上）。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination
from .enums import Subject


class Exam(BaseModel):
    """考试。独立实体，不是 Goal 的一种；Goal 用 examId + targetScore 引用它。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "examId": "e_3f21",
                "subject": "SX",
                "name": "期中考试",
                "examDate": "2026-11-05",
                "score": 118,
                "fullScore": 150,
                "createdAt": "2026-10-20T09:00:00+08:00",
                "updatedAt": "2026-11-06T20:30:00+08:00",
            }
        },
    )

    exam_id: str = Field(..., alias="examId")
    subject: Subject
    name: str = Field(..., max_length=64, description="考试名称，如「期中考试」")
    exam_date: date = Field(..., alias="examDate")
    score: float | None = Field(
        None, ge=0, description="得分。考后回填，回填前为 null（不做 0 值兜底：0 分与未回填是两回事）"
    )
    full_score: float = Field(..., alias="fullScore", gt=0)
    duration_minutes: int | None = Field(
        None,
        alias="durationMinutes",
        ge=1,
        le=600,
        description=(
            "考试时长（分钟）。存在的理由很具体：成绩回填要生成一条学习记录（D49 喂状态评估），"
            "而记录的学习时长必填——考试时长是客观事实，填了才生成记录，**不填就不生成**，"
            "绝不为了凑一条记录去编一个时长。"
        ),
    )
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt", description="最近更新时间（考试可编辑）")


class ExamCreate(BaseModel):
    """创建考试请求体。score 可当场填（刚考完）也可留空（考前先记下日程）。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "subject": "SX",
                "name": "期中考试",
                "examDate": "2026-11-05",
                "fullScore": 150,
            }
        },
    )

    subject: Subject
    name: str = Field(..., max_length=64)
    exam_date: date = Field(..., alias="examDate")
    full_score: float = Field(..., alias="fullScore", gt=0)
    score: float | None = Field(None, ge=0)
    duration_minutes: int | None = Field(None, alias="durationMinutes", ge=1, le=600)


class ExamUpdate(BaseModel):
    """考试局部更新，至少传一项（考后回填成绩就走这里）。"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"score": 118}},
    )

    name: str | None = Field(None, max_length=64)
    exam_date: date | None = Field(None, alias="examDate")
    full_score: float | None = Field(None, alias="fullScore", gt=0)
    score: float | None = Field(
        None, ge=0, description="得分；显式传 null 表示撤回回填（回到「未出分」）"
    )
    duration_minutes: int | None = Field(None, alias="durationMinutes", ge=1, le=600)


class ExamList(BaseModel):
    items: list[Exam]
    pagination: Pagination


class ExamDeleted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    deleted: bool
    exam_id: str = Field(..., alias="examId")

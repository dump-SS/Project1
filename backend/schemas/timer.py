"""专注计时（openapi.yaml `/timer-sessions` 系列）

TimerSession / TimerSegment / TimerSessionStart / TimerSegmentStart /
TimerRestore / TimerCurrent / TimerFinish / TimerDiscarded

字段名与枚举取值以 docs/openapi.yaml 为准（TimerSession / TimerSegment / TimerRestore
已在 M0 冻结，本模块补齐请求体与"当前会话"包装）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import Completion, Subject, TimerMode, TimerStatus
from .learning_record import RecordSelfReport


class TimerSegment(BaseModel):
    """计时会话内的一段（#14 分段计时）。一个会话可挂多段，每段标注所属任务。"""

    model_config = ConfigDict(populate_by_name=True)

    segment_id: str = Field(..., alias="segmentId")
    task_id: str | None = Field(None, alias="taskId", description="本段属于哪个任务；切换任务即新开一段")
    started_at: datetime = Field(..., alias="startedAt")
    ended_at: datetime | None = Field(None, alias="endedAt")
    seconds: int | None = Field(None, description="本段有效秒数（口径同 effectiveSeconds）")


class TimerSession(BaseModel):
    """计时会话（服务端持久化的"进行中"记录 = 专注态的唯一真相源）。"""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(..., alias="sessionId")
    mode: TimerMode
    started_at: datetime = Field(..., alias="startedAt", description="两种模式都有；恢复计算的基准")
    target_minutes: int | None = Field(None, alias="targetMinutes", description="仅 countdown 有；countup 为 null")
    plan_id: str | None = Field(None, alias="planId")
    task_id: str | None = Field(None, alias="taskId")
    subject: Subject
    status: TimerStatus
    ended_at: datetime | None = Field(None, alias="endedAt")
    effective_seconds: int | None = Field(
        None, alias="effectiveSeconds", description="**有效时长**（秒），≠ 墙上时长（D31）"
    )
    last_heartbeat_at: datetime | None = Field(None, alias="lastHeartbeatAt")
    segments: list[TimerSegment] = Field(default_factory=list, description="分段（#14）")
    created_at: datetime = Field(..., alias="createdAt")


class TimerSessionStart(BaseModel):
    """开始一次计时。

    `targetMinutes` 仅 countdown 必填；countup 传了会被忽略（不报错，避免前端切换模式时多余的 400）。
    `subject` 可不传——服务端会从 taskId 对应的计划任务推导，推不出来才兜底 `other`。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {"mode": "countdown", "targetMinutes": 30, "planId": "p_1a2b", "taskId": "t_3c4d"}
        },
    )

    mode: TimerMode
    target_minutes: int | None = Field(None, alias="targetMinutes", ge=1, le=600)
    plan_id: str | None = Field(None, alias="planId")
    task_id: str | None = Field(None, alias="taskId")
    subject: Subject | None = Field(None, description="不传则从 taskId 推导，推不出兜底 other")


class TimerSegmentStart(BaseModel):
    """切换任务 → 开新的一段（#14：一会话内分段，不允许并行计时）。"""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str | None = Field(None, alias="taskId", description="本段要做什么任务；不传表示自由学习")


class TimerRestore(BaseModel):
    """恢复视图（D30 按 mode 分支计算）。

    `needsVerdict=true` 表示识别到**异常会话**，前端必须弹**恢复裁决卡**（D31），**不得自动记账**。
    """

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(..., alias="sessionId")
    mode: TimerMode
    remaining_seconds: int | None = Field(
        None, alias="remainingSeconds", description="仅 countdown：剩余 = target − 已过；≤0 视为已到点（软提醒，不自动结束）"
    )
    elapsed_seconds: int | None = Field(None, alias="elapsedSeconds", description="仅 countup：累计 = now − startedAt")
    needs_verdict: bool = Field(..., alias="needsVerdict", description="是否需用户裁决（断连 / 超上限）")
    suggested_minutes: int | None = Field(
        None, alias="suggestedMinutes", description="裁决卡「保留按 X 记」的预填值（倒计时封顶 target；正计时按截断点）"
    )


class TimerCurrent(BaseModel):
    """`GET /timer-sessions/current`：当前是否有进行中的会话。

    用 `active` 包装而不是"没有就 404"：前端每次进计时页都会问一次，
    "没有会话"是**正常流程**而不是错误，不该走错误分支。
    """

    model_config = ConfigDict(populate_by_name=True)

    active: bool
    session: TimerSession | None = None
    restore: TimerRestore | None = None


class TimerFinish(BaseModel):
    """计时收尾（D20 三层形态：结束瞬间 0 步 → 轻收尾卡 → 正确率延后补）。

    必填只有 `completion`（唯一"半强制"问句）；`selfReport` **可整段省略**、
    其中专注/疲劳/情绪/难度**任一可缺**（软字段转译不出就留空，D34 不造数）。
    `durationMinutes` 显式传入时**覆盖服务端按 mode 算出的有效时长**——
    这正是裁决卡第三态「手动改时长」的落点。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "completion": "completed",
                "selfReport": {"focus": 4, "fatigue": 2, "emotion": "positive", "difficultyFeel": "moderate"},
                "note": "函数图像终于看懂了",
            }
        },
    )

    completion: Completion
    self_report: RecordSelfReport | None = Field(
        None, alias="selfReport", description="自评；可整段省略，软字段也可缺"
    )
    duration_minutes: int | None = Field(
        None, alias="durationMinutes", ge=1, le=600, description="不传则按 mode 算有效时长；传入即以它为准"
    )
    note: str | None = Field(None, max_length=100, description="≤100 字备注")
    skip_recommendation: bool | None = Field(None, alias="skipRecommendation")


class TimerDiscarded(BaseModel):
    """裁决卡「丢弃」的结果。**不产生学习记录**（D31 验收：僵尸会话不产生记录）。"""

    model_config = ConfigDict(populate_by_name=True)

    discarded: bool
    session_id: str = Field(..., alias="sessionId")

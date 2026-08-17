"""类型定义——严格对齐 docs/openapi.yaml components.schemas。

字段名、枚举取值均以 openapi.yaml 为准，不发明新字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


# ---------- 枚举（openapi.yaml §0.4） ----------

class Completion(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    ABANDONED = "abandoned"


class Emotion(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Trend(str, Enum):
    UP = "up"
    FLAT = "flat"
    DOWN = "down"


class StateLabel(str, Enum):
    EFFICIENT_STABLE = "efficient_stable"
    FATIGUE_WARNING = "fatigue_warning"
    EMOTION_BLOCKED = "emotion_blocked"
    FLUCTUATING_UP = "fluctuating_up"
    INSUFFICIENT_DATA = "insufficient_data"


# ---------- 输入数据（对应 RecordBehavior + RecordSelfReport） ----------

@dataclass(frozen=True, slots=True)
class BehaviorInput:
    """openapi.yaml RecordBehavior"""
    completion: Completion
    accuracy: float | None = None       # 0-1；无客观测验时为 None
    interruptions: int = 0
    blur_count: int = 0                  # openapi: blurCount


@dataclass(frozen=True, slots=True)
class SelfReportInput:
    """openapi.yaml RecordSelfReport"""
    focus: int          # 1-5
    fatigue: int        # 1-5
    emotion: Emotion
    difficulty_feel: Literal["easy", "moderate", "hard"]  # openapi: difficultyFeel


@dataclass(frozen=True, slots=True)
class RecordInput:
    """单次学习记录的计算输入。不包含 subject/startedAt 等与分数计算无关的元字段。"""
    behavior: BehaviorInput
    self_report: SelfReportInput
    duration_minutes: int = 0   # 用于加权平均时的参考，不参与分数公式


# ---------- 权重配置（PRD 5.2 第 1/4 点） ----------

@dataclass(slots=True)
class WeightConfig:
    """用户级权重表。所有权重存于后台配置与用户级权重表，不写死在代码逻辑里。

    约束（PRD 5.2 硬限制）：
    - alpha, beta ∈ [0.3, 0.7]，且 alpha + beta = 1
    - 行为子项 w1+w2+w3 归一化为 1，各 ∈ [0.1, 0.5]
    - 自评子项 w4+w5+w6 归一化为 1，各 ∈ [0.1, 0.5]
    """
    # 行为 vs 自评的主权重
    alpha: float = 0.5
    beta: float = 0.5
    # 行为子项（完成度 / 正确率 / 节奏稳定度）
    w1: float = 1 / 3
    w2: float = 1 / 3
    w3: float = 1 / 3
    # 自评子项（专注度 / 反向疲劳 / 情绪正向）
    w4: float = 1 / 3
    w5: float = 1 / 3
    w6: float = 1 / 3


# ---------- 输出 ----------

@dataclass(frozen=True, slots=True)
class SessionScore:
    """单次学习状态分（0-1），以及两个子分。"""
    score: float
    behavior_sub: float
    self_report_sub: float


@dataclass(frozen=True, slots=True)
class WindowAssessment:
    """滑动窗口评估结果——对应 openapi.yaml StateResult / AssessmentSnapshot。"""
    window_score: float | None      # 均值；data_sufficient=False 时为 None
    trend: Trend | None
    state_label: StateLabel
    data_sufficient: bool
    record_count: int
    # 可解释性：PRD 8.3 / 6.5
    signals: list[str] = field(default_factory=list)


# ---------- 标签判定阈值（PRD 明确说"待校准"，此处给合理初始值，通过配置传入） ----------

@dataclass(slots=True)
class LabelThresholds:
    """标签映射的数值阈值。PRD 5.2 注明"待算法实现阶段基于真实数据分布校准确定"，
    这里给出合理初始值，全部可通过配置覆盖。"""
    min_records: int = 3                # 低于此数为 insufficient_data
    high_score: float = 0.65            # windowScore >= 此值视为"水平高"
    low_score: float = 0.45             # windowScore <= 此值视为"水平低"
    slope_up: float = 0.03             # 回归斜率 >= 此值视为"明显上升"
    slope_down: float = -0.03          # 回归斜率 <= 此值视为"明显下降"
    fatigue_high: float = 4.0           # 疲劳自评 >= 此值视为"持续偏高"
    emotion_negative_streak: int = 2    # 连续 N 次负向情绪触发 emotion_blocked

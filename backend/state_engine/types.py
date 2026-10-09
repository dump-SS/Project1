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
    """openapi.yaml RecordSelfReport

    ⚠️ 四字段**全部可空**（2026-09-25 放开，原为必填）。依据目标态 §3.7(a)：
    三层收尾里唯一"半强制"的只有**完成度**；专注/疲劳/难度是模型从"一句感受"转译的
    **软字段**，情绪快捷词也只是"可选兜底"。转译不出就缺省——**不造数**（D34）。
    自评整段缺失的典型场景：考试成绩回填生成的记录。
    """
    focus: int | None = None                        # 1-5；None = 未采集
    fatigue: int | None = None                      # 1-5；None = 未采集
    emotion: Emotion | None = None                  # None = 未采集
    difficulty_feel: Literal["easy", "moderate", "hard"] | None = None  # openapi: difficultyFeel


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
    """单次学习状态分（0-1），以及两个子分。

    `self_report_sub` **可空**：自评整段缺失时（考试成绩回填记录）为 None。
    不能用 0.0 冒充——0.0 的含义是"自评很差"，会把窗口分数整体拉低，那是另一种造数。
    """
    score: float
    behavior_sub: float
    self_report_sub: float | None


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
    这里给出合理初始值，全部可通过配置覆盖。

    high_score 曾设为 0.65，实测默认权重下典型记录集中在 0.7-0.9，
    导致几乎所有场景都落入 efficient_stable，标签区分度失效；上调到 0.75。
    """
    min_records: int = 3                # 低于此数为 insufficient_data
    high_score: float = 0.75            # windowScore >= 此值视为"水平高"
    low_score: float = 0.45             # windowScore <= 此值视为"水平低"
    slope_up: float = 0.03             # 回归斜率 >= 此值视为"明显上升"
    slope_down: float = -0.03          # 回归斜率 <= 此值视为"明显下降"
    fatigue_high: float = 4.0           # 疲劳自评 >= 此值视为"持续偏高"
    emotion_negative_streak: int = 2    # 连续 N 次负向情绪触发 emotion_blocked

"""单次学习状态分计算 — PRD 5.2 第 1 点。

公式固定，权重可由 AI 调整（但调整幅度受硬限制约束，见 weights.py）。
本模块**只负责一次学习记录的打分**，趋势和标签见 assessment.py。
"""

from __future__ import annotations

from .types import (
    BehaviorInput,
    Completion,
    Emotion,
    RecordInput,
    SelfReportInput,
    SessionScore,
    WeightConfig,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------- 归一化函数（0-1） ----------

def normalize_completion(completion: Completion) -> float:
    """完成度 → 0-1。三级枚举，completed=1, partial=0.5, abandoned=0。"""
    match completion:
        case Completion.COMPLETED:
            return 1.0
        case Completion.PARTIAL:
            return 0.5
        case Completion.ABANDONED:
            return 0.0


def normalize_rhythm(interruptions: int, blur_count: int) -> float:
    """节奏稳定度（中断次数的反向标准化）。

    PRD 只写了"中断次数的反向标准化"，未定义具体函数形态。
    这里用 1 / (1 + total_disturbances/5) 做平滑衰减：
    - 0 次中断 → 1.0
    - 5 次中断 → 0.5
    - 15 次中断 → 0.25
    分母 5 是调参旋钮，通过配置可改（暂不暴露，后续有数据再调）。

    负值输入按 0 处理，保证函数自洽（不依赖外层 clamp 兜底）。
    """
    total = max(0, interruptions + blur_count)
    return 1.0 / (1.0 + total / 5.0)


def normalize_focus(focus: int) -> float:
    """专注度 1-5 → 0-1。"""
    return (focus - 1) / 4.0


def normalize_inverse_fatigue(fatigue: int) -> float:
    """PRD 公式：(6 - fatigue) 归一化到 0-1。fatigue=1→1.0, fatigue=5→0.2。"""
    return (6 - fatigue - 1) / 4.0


def normalize_emotion(emotion: Emotion) -> float:
    """情绪正向程度：positive=1, neutral=0.5, negative=0。"""
    match emotion:
        case Emotion.POSITIVE:
            return 1.0
        case Emotion.NEUTRAL:
            return 0.5
        case Emotion.NEGATIVE:
            return 0.0


# ---------- 核心计算 ----------

def _redistribute_behavior_weights(w: WeightConfig, has_accuracy: bool) -> tuple[float, float, float]:
    """accuracy 缺失时，w2 归零并重新分配给 w1、w3（PRD 5.2：该项权重归零并重新分配）。"""
    if has_accuracy:
        return w.w1, w.w2, w.w3
    # w2 归零，w1 和 w3 按原比例重分配
    remaining = w.w1 + w.w3
    if remaining == 0:
        return 0.5, 0.0, 0.5
    return w.w1 / remaining, 0.0, w.w3 / remaining


def compute_session_score(record: RecordInput, weights: WeightConfig) -> SessionScore:
    """计算单次学习状态分。

    PRD 5.2 第 1 点：
        行为子分 = w1×完成度 + w2×正确率 + w3×节奏稳定度
        自评子分 = w4×专注度 + w5×(6-疲劳度) + w6×情绪正向程度
        单次状态分 = α×行为子分 + β×自评子分
    """
    b = record.behavior
    s = record.self_report

    # 行为子分
    has_accuracy = b.accuracy is not None
    bw1, bw2, bw3 = _redistribute_behavior_weights(weights, has_accuracy)

    completion_val = normalize_completion(b.completion)
    accuracy_val = b.accuracy if has_accuracy else 0.0
    rhythm_val = normalize_rhythm(b.interruptions, b.blur_count)

    behavior_sub = _clamp01(bw1 * completion_val + bw2 * accuracy_val + bw3 * rhythm_val)

    # 自评子分
    focus_val = normalize_focus(s.focus)
    fatigue_val = normalize_inverse_fatigue(s.fatigue)
    emotion_val = normalize_emotion(s.emotion)

    self_report_sub = _clamp01(weights.w4 * focus_val + weights.w5 * fatigue_val + weights.w6 * emotion_val)

    # 总分
    score = _clamp01(weights.alpha * behavior_sub + weights.beta * self_report_sub)

    return SessionScore(score=score, behavior_sub=behavior_sub, self_report_sub=self_report_sub)

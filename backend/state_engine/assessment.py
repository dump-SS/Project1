"""滑动窗口趋势量化 + 状态标签判定 — PRD 5.2 第 2/3 点。

输入：一批 SessionScore（最近 N 次或最近 N 天的记录）+ 原始 selfReport 序列（用于标签信号）。
输出：WindowAssessment（均值、趋势、标签、可解释信号）。
"""

from __future__ import annotations

from .types import (
    Emotion,
    LabelThresholds,
    RecordInput,
    SessionScore,
    StateLabel,
    Trend,
    WindowAssessment,
)


def _linear_slope(values: list[float]) -> float:
    """简单线性回归斜率（PRD：不需要复杂时序模型）。x = 0,1,2,...,n-1。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _determine_trend(slope: float, thresholds: LabelThresholds) -> Trend:
    if slope >= thresholds.slope_up:
        return Trend.UP
    if slope <= thresholds.slope_down:
        return Trend.DOWN
    return Trend.FLAT


def _determine_label(
    mean_score: float,
    trend: Trend,
    records: list[RecordInput],
    thresholds: LabelThresholds,
) -> tuple[StateLabel, list[str]]:
    """PRD 5.2 第 3 点的标签映射。返回 (标签, 可解释信号列表)。

    PRD 注明阈值待校准，这里用 LabelThresholds 的可配置默认值。
    """
    signals: list[str] = []

    # 检测疲劳持续偏高
    recent_fatigues = [r.self_report.fatigue for r in records[-3:]]
    fatigue_high = (
        len(recent_fatigues) >= 2
        and all(f >= thresholds.fatigue_high for f in recent_fatigues)
    )
    if fatigue_high:
        signals.append(f"自评疲劳度连续 {len(recent_fatigues)} 次 ≥{thresholds.fatigue_high:.0f}")

    # 检测情绪连续负向
    recent_emotions = [r.self_report.emotion for r in records[-thresholds.emotion_negative_streak:]]
    emotion_blocked = (
        len(recent_emotions) >= thresholds.emotion_negative_streak
        and all(e == Emotion.NEGATIVE for e in recent_emotions)
    )
    if emotion_blocked:
        signals.append(f"情绪自评连续 {thresholds.emotion_negative_streak} 次为负向")

    # 标签判定逻辑（按优先级，先匹配先中）
    if emotion_blocked and trend in (Trend.DOWN, Trend.FLAT):
        return StateLabel.EMOTION_BLOCKED, signals

    # 疲劳预警：疲劳信号 + （水平不高 或 趋势下降）。
    # 仅在有疲劳信号或水平确实低时才预警——之前的实现把兜底分支无条件给
    # fatigue_warning，导致「中等+平稳、无任何负面信号」的用户被莫名预警。
    if fatigue_high and (mean_score < thresholds.high_score or trend == Trend.DOWN):
        signals.append("疲劳自评持续偏高，状态水平不高或趋势下降")
        return StateLabel.FATIGUE_WARNING, signals

    if mean_score >= thresholds.high_score and trend in (Trend.FLAT, Trend.UP):
        signals.append("状态水平高且趋势平稳或上升")
        return StateLabel.EFFICIENT_STABLE, signals

    if trend == Trend.UP and mean_score < thresholds.high_score:
        signals.append("趋势明显上升但水平尚未达高位")
        return StateLabel.FLUCTUATING_UP, signals

    # 低水平：无论趋势如何都值得提醒
    if mean_score <= thresholds.low_score:
        signals.append("状态水平偏低，建议调整学习节奏")
        return StateLabel.FATIGUE_WARNING, signals

    # 以下兜底分支逐项附信号，保证「标签 + 可解释性」不脱节：
    # 高水平 + 下降趋势（均值高掩盖了近期下滑，趋势信号必须给出）
    if mean_score >= thresholds.high_score:
        signals.append("状态水平高但近期趋势下降，留意状态变化")
        return StateLabel.EFFICIENT_STABLE, signals
    # 中等水平 + 下降趋势
    if trend == Trend.DOWN:
        signals.append("状态水平中等且趋势下降，建议调整节奏")
        return StateLabel.FATIGUE_WARNING, signals
    # 中等水平 + 平稳，无负面信号：不强行预警，如实标注
    if trend == Trend.FLAT:
        signals.append("状态水平一般但保持平稳")
        return StateLabel.EFFICIENT_STABLE, signals
    # 防御性兜底（正常不应到达）
    signals.append("状态波动，建议观察")
    return StateLabel.FATIGUE_WARNING, signals


def compute_window_assessment(
    scores: list[SessionScore],
    records: list[RecordInput],
    thresholds: LabelThresholds | None = None,
) -> WindowAssessment:
    """PRD 5.2 第 2/3 点：滑动窗口趋势 + 标签。

    Args:
        scores: 窗口内各条记录的 SessionScore（按时间正序）
        records: 对应的原始 RecordInput（用于标签信号检测）
        thresholds: 标签阈值配置，不传用默认值

    Returns:
        WindowAssessment
    """
    if thresholds is None:
        thresholds = LabelThresholds()

    n = len(scores)

    # 冷启动：PRD「记录次数低于最小阈值时不下结论」
    if n < thresholds.min_records:
        return WindowAssessment(
            window_score=None,
            trend=None,
            state_label=StateLabel.INSUFFICIENT_DATA,
            data_sufficient=False,
            record_count=n,
            signals=[f"记录仅 {n} 条，需至少 {thresholds.min_records} 条"],
        )

    values = [s.score for s in scores]
    mean_score = sum(values) / n
    slope = _linear_slope(values)
    trend = _determine_trend(slope, thresholds)
    label, signals = _determine_label(mean_score, trend, records, thresholds)

    return WindowAssessment(
        window_score=round(mean_score, 4),
        trend=trend,
        state_label=label,
        data_sufficient=True,
        record_count=n,
        signals=signals,
    )

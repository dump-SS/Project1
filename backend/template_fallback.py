"""规则模板兜底（PRD 5.3：API 超时/失败/审核不通过时回退到模板库）。

按「状态标签 + 学科 + 计划执行情况」三维匹配建议模板，
比 mock-server 的单条 focus/fatigue 判断更贴合 PRD 要求。
用户始终能拿到可用建议，不出现空白。
"""

from __future__ import annotations

from state_engine.types import StateLabel

__all__ = [
    "build_template_recommendation",
    "build_template_summary",
    "RecommendationItem",
]

RecommendationItem = dict  # { "title": str, "content": str }

SUBJECT_CN = {
    "YW": "语文", "SX": "数学", "YY": "英语",
    "WL": "物理", "HX": "化学", "SW": "生物",
    "LS": "历史", "DL": "地理", "ZZ": "政治", "other": "学习",
}


def _subject_cn(subject: str | None) -> str:
    return SUBJECT_CN.get(subject or "", "学习")


def build_template_recommendation(
    state_label: str,
    subject: str | None,
    record_focus: int | None = None,
    record_fatigue: int | None = None,
    plan_completion_ratio: float | None = None,
) -> tuple[list[RecommendationItem], str]:
    """按状态标签匹配建议模板。

    返回 (items, explain)：
    - items: [{title, content}] 列表，至少一条
    - explain: 面向用户的依据说明（填 basedOn.explain）
    """
    subj = _subject_cn(subject)
    items: list[RecommendationItem] = []

    match state_label:
        case StateLabel.FATIGUE_WARNING.value:
            items.append({
                "title": f"把{subj}单次时长压到 25 分钟",
                "content": f"最近{subj}的疲劳感比较明显，建议下次把单次专注时长缩短到 25 分钟左右，中间安排 5 分钟休息，恢复精力再继续。",
            })
            if record_fatigue and record_fatigue >= 4:
                items.append({
                    "title": "先巩固再上新",
                    "content": "这次疲劳度偏高，暂时别急着推进新内容，明天先把已掌握的题型过一遍找回手感。",
                })
            explain = f"依据最近{subj}状态标签（疲劳预警）与自评疲劳度"

        case StateLabel.EMOTION_BLOCKED.value:
            items.append({
                "title": "主动降低下一次任务量",
                "content": f"最近{subj}学习时情绪有些受阻，建议把下一次的任务量降下来。降低目标不等于放弃目标，调整节奏是为了走得更远。",
            })
            explain = f"依据最近{subj}状态标签（情绪受阻）与情绪自评连续负向"

        case StateLabel.EFFICIENT_STABLE.value:
            items.append({
                "title": "保持这个节奏",
                "content": f"最近{subj}的状态高效且稳定，这个学习时段和节奏挺适合你，可以继续沿用。",
            })
            if plan_completion_ratio is not None and plan_completion_ratio >= 0.8:
                items.append({
                    "title": "适度增加拔高内容",
                    "content": "计划完成情况不错，状态又稳定，可以试着引入一些拔高题或提前进入下一阶段目标。",
                })
            explain = f"依据最近{subj}状态标签（高效稳定）与计划完成情况"

        case StateLabel.FLUCTUATING_UP.value:
            items.append({
                "title": "趁势稳住节奏",
                "content": f"最近{subj}的状态正在回升，趁这个势头把节奏稳住，不用急着加量，保持住就好。",
            })
            explain = f"依据最近{subj}状态标签（波动上升）与趋势变化"

        case _:
            # insufficient_data 或其他：兜底平稳文案
            items.append({
                "title": "平稳完成，继续保持",
                "content": "这次的专注时长和自评都比较平稳，按自己的节奏来，积累下去会看到变化的。",
            })
            explain = "依据本次学习记录的自评数据"

    return items, explain


def build_template_summary(
    record_count: int,
    subjects: list[str],
    plan_completion_ratio: float | None,
    state_labels: list[str],
) -> dict:
    """规则模板版复盘内容（MVP 阶段 MockProvider 时使用）。

    返回 SummaryContent 形状的 dict（overview/patterns/suggestions/encouragement）。
    真实 LLM 接入后此函数仍作为兜底保留，但 PRD 5.4 说复盘不做兜底——
    所以这个函数实际上只在 MockProvider 开发阶段被调用，生产环境复盘失败直接 failed。
    """
    subj_str = "、".join(_subject_cn(s) for s in subjects) if subjects else "各学科"
    ratio_str = f"{plan_completion_ratio:.0%}" if plan_completion_ratio is not None else "未知"

    overview = f"这段时间共记录 {record_count} 次学习，涵盖 {subj_str}，计划完成率 {ratio_str}。"
    if StateLabel.FATIGUE_WARNING.value in state_labels:
        overview += "整体来看有疲劳预警信号，建议适当放慢节奏。"
    elif StateLabel.EFFICIENT_STABLE.value in state_labels:
        overview += "整体状态高效稳定，保持住这个节奏。"
    else:
        overview += "状态有起伏，属正常波动。"

    patterns = []
    if StateLabel.FATIGUE_WARNING.value in state_labels:
        patterns.append("疲劳预警出现的那几天，学习时长和完成度都明显低于其他天")
    if plan_completion_ratio is not None and plan_completion_ratio < 0.6:
        patterns.append(f"计划完成率仅 {ratio_str}，可能目标定得偏高或时间安排不够充裕")

    suggestions = []
    if StateLabel.FATIGUE_WARNING.value in state_labels:
        suggestions.append("下周把单次学习时长整体下调 20%，先稳住状态再加量")
    suggestions.append("保持记录习惯，数据越完整，状态判断越准")

    encouragement = "状态有起伏很正常，坚持记录本身就是一种成长。"

    return {
        "overview": overview,
        "patterns": patterns,
        "suggestions": suggestions,
        "encouragement": encouragement,
    }

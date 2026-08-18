"""内容安全审核层（PRD 6.3）。

三层结合，不依赖单一手段：
1. 关键词/正则黑名单（心理诊断、贬低打击、医疗用药、自伤信号）
2. 危机信号识别 → 走硬编码审定文案，不过 LLM
3. （供应商侧内容安全能力留作后续接入）

审核不通过 → 建议走模板兜底、复盘走 failed。
"""

from __future__ import annotations

import re

__all__ = ["check", "is_crisis_signal", "CRISIS_RESPONSE"]

# PRD 6.3 禁止内容的关键词/正则
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"抑郁|焦虑症|抑郁症|心理疾病|精神分裂|双相|强迫症",  # 心理诊断/病理化
        r"自杀|自残|自伤|轻生|不想活|了结自己|结束生命",  # 自伤/危机
        r"你真笨|你太蠢|没救了|废物|一无是处|烂泥扶不上墙",  # 贬低打击
        r"吃药|服药|抗抑郁药|安眠药|药物剂量",  # 医疗用药
        r"再熬一晚|通宵|别睡了|熬夜刷题",  # 鼓励过度学习损害健康
    ]
]

# 危机信号 → 固定审定文案（PRD 6.3：硬编码，不走 LLM）
CRISIS_RESPONSE = (
    "如果你最近感到压力很大或情绪低落，这很正常，和信任的家人、老师聊一聊会有帮助。"
    "也可以拨打心理援助热线 12355。你不必独自面对。"
)


def is_crisis_signal(text: str) -> bool:
    """检测文本是否包含自伤/危机信号。"""
    return any(p.search(text) for p in _BLOCKED_PATTERNS[1:2])  # 自伤/危机那组


def check(content: str) -> tuple[bool, str | None]:
    """审核生成内容。

    Returns:
        (passed, reason): passed=True 表示可通过；passed=False 时 reason 说明拦截原因。
        危机信号不在此函数处理（由 ai_suggestion 在调用前判断，走 CRISIS_RESPONSE）。
    """
    for pattern in _BLOCKED_PATTERNS:
        match = pattern.search(content)
        if match:
            return False, f"内容安全审核拦截：命中禁止类别「{_pattern_name(pattern)}」"
    return True, None


def _pattern_name(pattern: re.Pattern[str]) -> str:
    """给命中的 pattern 一个人类可读的名字（用于日志/留痕）。"""
    text = pattern.pattern
    if "自杀" in text or "自伤" in text:
        return "自伤/危机信号"
    if "抑郁" in text or "心理疾病" in text:
        return "心理诊断/病理化表述"
    if "笨" in text or "废物" in text:
        return "贬低打击性评价"
    if "吃药" in text or "药" in text:
        return "医疗/用药建议"
    if "熬夜" in text or "通宵" in text:
        return "鼓励过度学习"
    return "未知禁止类别"

"""敏感信息脱敏层（PRD 6.2 数据出域边界）。

PRD 6.2 要求：对用户输入做敏感信息检测（如手机号、身份证号模式匹配），
命中时在发送前脱敏或阻断。

本模块负责在用户文本（学习记录 note、目标 description 等）进入 LLM prompt 前
做脱敏：把手机号、身份证号、邮箱、QQ 号等替换为 ***，避免敏感信息出域。

策略选择（脱敏而非阻断）：
- 阻断会让用户困惑（"为什么我的备注被拒"），且 note 主体可能是有用上下文。
- 脱敏保留了上下文语义（"给 138****5678 打电话" 仍能看出是"打电话"行为），
  同时抹去了真实号码。
- 危机信号、内容安全仍由 safety_filter 在 LLM 输出侧把关（PRD 6.3）。
"""
from __future__ import annotations

import re

__all__ = ["sanitize_text", "contains_sensitive_info", "SENSITIVE_PATTERN_NAMES"]


# 敏感信息正则（按检测优先级排序）
# 1. 身份证号（18 位，最后一位可能是 X）：前 6 位地区码 + 8 位生日 + 3 位顺序 + 1 位校验
#    宽松匹配：避免误判 17 位数字串，要求 18 位且符合基本结构
_ID_CARD = re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")

# 2. 手机号：1 开头 11 位（中国大陆）。宽松边界，避免误匹配长数字串
_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# 3. 邮箱（监护人联系方式可能被学生填进 note）
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# 4. QQ 号：5-12 位纯数字（边界限制，避免误判短数字）
_QQ = re.compile(r"(?<!\d)[1-9]\d{4,11}(?!\d)")

# 按顺序检测：身份证优先（最长），再手机，再邮箱，再 QQ
# 注意：手机号正则可能误匹配身份证中间段，所以身份证先处理
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("身份证号", _ID_CARD),
    ("手机号", _MOBILE),
    ("邮箱", _EMAIL),
    ("QQ号", _QQ),
]


def contains_sensitive_info(text: str) -> tuple[bool, list[str]]:
    """检测文本是否包含敏感信息。

    Returns:
        (has_sensitive, names): has_sensitive=True 时 names 列出命中的类别。
    """
    if not text:
        return False, []
    names: list[str] = []
    for name, pattern in _PATTERNS:
        if pattern.search(text):
            names.append(name)
    return bool(names), names


def sanitize_text(text: str | None) -> str | None:
    """脱敏用户文本：把敏感信息替换为 ***。

    None 或空字符串原样返回。脱敏后的文本保留上下文语义，
    仅抹去真实号码/邮箱，可安全出域给 LLM。

    替换策略：整段匹配替换为 ***（不保留前几位），避免可逆推。
    """
    if not text:
        return text

    result = text
    for _name, pattern in _PATTERNS:
        result = pattern.sub("***", result)
    return result


# 供日志/测试引用的模式名列表
SENSITIVE_PATTERN_NAMES = [name for name, _ in _PATTERNS]

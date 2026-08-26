"""
枚举字典（openapi.yaml 0.4 节）

Subject / Stage / GoalType / TaskStatus / Completion / Emotion / DifficultyFeel
Trend / StateLabel / RecScene / GenerationSource / Rating
"""
from __future__ import annotations

from enum import Enum


class Subject(str, Enum):
    """学科代码（拼音首字母大写，2026-08-26 与知识点库标准对齐；other 保留兜底）。

    取值固定，禁止自造：YW 语文 / SX 数学 / YY 英语 / WL 物理 / HX 化学 /
    SW 生物 / ZZ 思想政治 / LS 历史 / DL 地理。
    """
    yw = "YW"      # 语文
    sx = "SX"      # 数学
    yy = "YY"      # 英语
    wl = "WL"      # 物理
    hx = "HX"      # 化学
    sw = "SW"      # 生物
    zz = "ZZ"      # 思想政治
    ls = "LS"      # 历史
    dl = "DL"      # 地理
    other = "other"  # 兜底（冷启动计划/建议降级）


class Stage(str, Enum):
    junior = "junior"
    senior = "senior"


class GoalType(str, Enum):
    short_term = "short_term"
    long_term = "long_term"


class TaskStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    partial = "partial"
    abandoned = "abandoned"


# completion 比 taskStatus 少了 pending（已经在进行的任务不算完成度）
class Completion(str, Enum):
    completed = "completed"
    partial = "partial"
    abandoned = "abandoned"


class Emotion(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class DifficultyFeel(str, Enum):
    easy = "easy"
    moderate = "moderate"
    hard = "hard"


class Trend(str, Enum):
    up = "up"
    flat = "flat"
    down = "down"


class StateLabel(str, Enum):
    efficient_stable = "efficient_stable"
    fatigue_warning = "fatigue_warning"
    emotion_blocked = "emotion_blocked"
    fluctuating_up = "fluctuating_up"
    insufficient_data = "insufficient_data"


class RecScene(str, Enum):
    post_session = "post_session"
    weekly_review = "weekly_review"
    post_session_knowledge = "post_session_knowledge"  # 板块二内容维度建议（v2.2）


class GenerationSource(str, Enum):
    llm = "llm"
    template = "template"


class Rating(str, Enum):
    useful = "useful"
    neutral = "neutral"
    not_useful = "not_useful"

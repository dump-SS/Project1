"""单日学习总结生成（PRD 5.3 一日一句话总结）。

区别于 /summaries（3-31 天复盘）：本模块针对「某一天」生成 1 句话总结，
供个人数据页"学习情况"模块的日详情面板使用。

设计取舍：
- 不持久化：单日总结是派生态，前端按需拉取/前端可缓存；
  写入 ORM 会让"加一个总结字段"反复涉及表迁移，违反"功能竖切"原则。
- 不异步化：单次 LLM 调用 60s 上限 + 实时性诉求（用户在打卡页等待展开日详情），
  与 PRD 6.4 的"建议异步化"要求不同，本场景接受同步阻塞。
- 复用现有 LLM 抽象（llm_provider），供应商切换只需改 .env。
- 失败兜底：LLM 失败/数据不足时返回规则模板句，让前端永远有可显示内容。
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from llm_provider import get_provider
from models.learning_record import LearningRecord as LearningRecordORM

logger = logging.getLogger(__name__)


# 单日总结的最少记录数：少于此数视为"无意义总结"，走兜底句
MIN_RECORDS_FOR_DAY_SUMMARY = 1

# 单日总结的字数上限（PRD 5.3：1 句话）
# 经验值：模型在 60 字内容易半句话（缺主语/状态词），120 字能完整承载"事实+状态倾向"，
# 且仍属"一句话"范畴（移动端单行 ~28 字，两行内可读）。
MAX_SUMMARY_CHARS = 120


def _day_bounds(date_str: str) -> tuple[datetime, datetime]:
    """'YYYY-MM-DD' → 当日 [00:00:00, 23:59:59.999999] 闭区间。"""
    d = _date.fromisoformat(date_str)
    start = datetime(d.year, d.month, d.day)
    end = datetime(d.year, d.month, d.day, 23, 59, 59, 999999)
    return start, end


def _fetch_day_records(db: Session, user_id: str, date_str: str) -> list[LearningRecordORM]:
    start, end = _day_bounds(date_str)
    return db.execute(
        select(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.started_at >= start,
            LearningRecordORM.started_at <= end,
        )
        .order_by(LearningRecordORM.started_at.asc())
    ).scalars().all()


def _aggregate(records: Iterable[LearningRecordORM]) -> dict:
    """聚合当日记录为可喂给 LLM 的结构化数据。

    出于隐私（PRD 6.2），note 不入 prompt，只用结构化特征。
    """
    records = list(records)
    if not records:
        return {}
    total_minutes = sum(r.duration_minutes for r in records)
    subjects: dict[str, int] = {}
    for r in records:
        subjects[r.subject] = subjects.get(r.subject, 0) + r.duration_minutes
    # 完成情况统计
    completion = {"completed": 0, "partial": 0, "abandoned": 0}
    for r in records:
        c = r.behavior_completion
        if c in completion:
            completion[c] += 1
    # 自评均值（用于 LLM 调"状态"语气）
    focus_avg = sum(r.self_report_focus for r in records) / len(records)
    fatigue_avg = sum(r.self_report_fatigue for r in records) / len(records)
    # 情绪
    emotions = [r.self_report_emotion for r in records]
    positive = emotions.count("positive")
    negative = emotions.count("negative")
    return {
        "recordCount": len(records),
        "totalMinutes": total_minutes,
        "subjects": [{"name": s, "minutes": m} for s, m in sorted(subjects.items(), key=lambda x: -x[1])],
        "completion": completion,
        "focusAvg": round(focus_avg, 1),
        "fatigueAvg": round(fatigue_avg, 1),
        "positiveCount": positive,
        "negativeCount": negative,
    }


def _build_prompt(stats: dict, date_str: str) -> tuple[str, str]:
    """构造 LLM 调用的 (system, user) 提示词。

    硬约束（system）：
    - 一句话，≤60 字
    - 不评价对错、不给绝对化建议
    - 用第二人称「你」称呼用户
    - 不暴露模型身份
    """
    system = (
        "你是 EpochX 学习助手，给学生写一日学习总结。"
        "硬约束：1) 只输出 1 句话，不超过 120 字；2) 用第二人称「你」称呼；"
        "3) 不评价对错、不给绝对化建议；4) 不出现「作为 AI」、「我无法」等元话语；"
        "5) 聚焦客观事实（时长、学科、状态），避免编造数据；"
        "6) 写完整一句话，不要用省略号或截断；7) 不加标题或列表前缀。"
    )
    subjects_str = "、".join(f"{s['name']}（{s['minutes']}分钟）" for s in stats["subjects"][:3])
    completed = stats["completion"].get("completed", 0)
    partial = stats["completion"].get("partial", 0)
    abandoned = stats["completion"].get("abandoned", 0)
    completion_str = (
        f"完成 {completed} 次，部分完成 {partial} 次"
        + (f"，放弃 {abandoned} 次" if abandoned else "")
    )
    mood_str = ""
    if stats["positiveCount"] > stats["negativeCount"]:
        mood_str = "整体状态积极"
    elif stats["negativeCount"] > stats["positiveCount"]:
        mood_str = "略有疲态"
    else:
        mood_str = "状态平稳"

    user = (
        f"日期：{date_str}\n"
        f"学习总时长：{stats['totalMinutes']} 分钟（{stats['recordCount']} 段）\n"
        f"学科分布：{subjects_str or '无'}\n"
        f"完成情况：{completion_str}\n"
        f"专注度均值：{stats['focusAvg']}/5；疲劳度均值：{stats['fatigueAvg']}/5\n"
        f"情绪倾向：{mood_str}\n\n"
        "请根据以上事实写一句话总结。"
    )
    return system, user


def _fallback_summary(stats: dict, date_str: str) -> str:
    """LLM 失败 / MockProvider 返回 None / 数据不足时的兜底句。"""
    total = stats.get("totalMinutes", 0)
    count = stats.get("recordCount", 0)
    if total == 0 or count == 0:
        return f"{date_str} 没有记录，调整好节奏再出发。"
    subjects = stats.get("subjects", [])
    if not subjects:
        return f"今天共学习 {total} 分钟，{count} 个专注段。"
    main = subjects[0]
    return f"今天在 {main['name']} 上花了 {main['minutes']} 分钟，继续保持。"


def _truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """超长截断（尽量在句末标点处结束，避免半句话）。

    若 80% 范围内已有句末标点（。！？.!?），优先在那里截断；
    否则在 limit 字符处硬截并加 …。
    """
    text = text.strip().strip("。. \n")
    if len(text) <= limit:
        return text + "。"
    # 80% 范围内找最后一个句末标点
    head = text[: int(limit * 0.8)]
    cut = max(head.rfind("。"), head.rfind("！"), head.rfind("？"), head.rfind("!"), head.rfind("?"))
    if cut >= int(limit * 0.4):  # 太靠前（< 40%）说明本来就短，不需要截
        return text[: cut + 1]
    return text[: limit - 1] + "…"


def generate_day_summary(db: Session, user_id: str, date_str: str) -> str:
    """生成单日一句话总结（PRD 5.3）。

    Returns:
        一句话总结（≤60 字，末尾必有句号）。
        失败/无数据时返回兜底句。
    """
    records = _fetch_day_records(db, user_id, date_str)
    if len(records) < MIN_RECORDS_FOR_DAY_SUMMARY:
        return _fallback_summary({}, date_str)

    stats = _aggregate(records)
    system, user = _build_prompt(stats, date_str)

    try:
        provider = get_provider()
        text = provider.generate(user, context={"system": system})
    except Exception as e:  # noqa: BLE001 — 任何 LLM 异常都降级
        logger.warning("[DAY_SUMMARY] LLM 调用异常: %s: %s", type(e).__name__, e)
        text = None

    if not text:
        logger.info("[DAY_SUMMARY] LLM 未返回文本，走兜底")
        return _fallback_summary(stats, date_str)

    return _truncate(text)

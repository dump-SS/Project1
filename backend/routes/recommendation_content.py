"""导学计划页推荐内容生成（PRD 5.3 + 6.4）。

与 /recommendations 的区别：
- /recommendations：基于已有学习记录做完整建议（focus、study_plan、post_session 三种场景）
- 本接口：用于"导学计划"页顶部学习内容推荐块，只生成"主推学习内容 + 简短理由"
  - 入参：用户最近学习记录摘要 + 目标（可选）
  - 出参：subject / topic / reason / from_llm
  - 数据量阈值：最近 7 天至少 3 条有效学习记录才显示入口（PRD 8.3 数据脱敏）
  - 失败兜底：返回 plan.tasks[0] 拼字符串（与历史 StudyGuide 行为一致）

LLM 接入复用 llm_provider；切到 mock 模式时走兜底句，行为不会破。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from llm_provider import get_provider
from models.goal import Goal as GoalORM
from models.learning_record import LearningRecord as LearningRecordORM
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendation-content", tags=["导学计划推荐"])


# 数据量阈值：最近 7 天少于该值的用户不显示推荐入口
MIN_RECENT_RECORDS = 3
RECENT_WINDOW_DAYS = 7


class RecommendationContentResponse(BaseModel):
    """推荐内容响应。"""

    model_config = ConfigDict(populate_by_name=True)

    eligible: bool = Field(..., description="数据量是否达到阈值；false 时 from_llm=false, reason 是占位说明")
    record_count: int = Field(..., alias="recordCount")
    recent_window_days: int = Field(RECENT_WINDOW_DAYS, alias="recentWindowDays")
    subject: str | None = None
    topic: str | None = None
    reason: str
    from_llm: bool = Field(..., alias="fromLLM")


def _aggregate_recent_records(db: Session, user_id: str) -> dict[str, Any]:
    """聚合最近 N 天的学习记录 + 目标，给 LLM 做上下文。"""
    cutoff = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS)
    rows = db.execute(
        select(LearningRecordORM)
        .where(
            LearningRecordORM.user_id == user_id,
            LearningRecordORM.started_at >= cutoff,
        )
        .order_by(LearningRecordORM.started_at.desc())
        .limit(10)  # 给 LLM 看最近 10 条
    ).scalars().all()

    # 学科时长聚合
    subject_minutes: dict[str, int] = {}
    for r in rows:
        subject_minutes[r.subject] = subject_minutes.get(r.subject, 0) + r.duration_minutes
    # 排序：时长降序
    subjects_sorted = sorted(subject_minutes.items(), key=lambda x: -x[1])

    # 完成情况
    completion = {"completed": 0, "partial": 0, "abandoned": 0}
    for r in rows:
        if r.behavior_completion in completion:
            completion[r.behavior_completion] += 1

    # 平均自评
    focus_avg = sum(r.self_report_focus for r in rows) / max(len(rows), 1)
    fatigue_avg = sum(r.self_report_fatigue for r in rows) / max(len(rows), 1)

    # 目标（PRD 5.2：建议要参考活跃目标）
    goals = db.execute(
        select(GoalORM)
        .where(GoalORM.user_id == user_id, GoalORM.status == "active")
        .order_by(GoalORM.created_at.asc())
    ).scalars().all()
    goal_topics = [g.topic for g in goals[:3]]

    return {
        "recordCount": len(rows),
        "subjects": [{"name": s, "minutes": m} for s, m in subjects_sorted[:3]],
        "completion": completion,
        "focusAvg": round(focus_avg, 1),
        "fatigueAvg": round(fatigue_avg, 1),
        "activeGoals": goal_topics,
    }


def _build_prompt(features: dict) -> tuple[str, str]:
    """构造 LLM 调用的 (system, user) 提示词。

    硬约束：
    - 输出 1 句话 ≤60 字
    - 用第二人称「你」
    - JSON 格式：{"subject": "math", "topic": "推荐的具体学习主题", "reason": "简短理由"}
    """
    system = (
        "你是 EpochX 学习助手，给学生推荐下一个学习内容。\n"
        "硬约束：\n"
        "1) 输出 JSON：{\"subject\":\"<学科枚举>\",\"topic\":\"<具体主题>\",\"reason\":\"<理由,≤50字>\"}\n"
        "2) subject 必须是以下之一：chinese, math, english, physics, chemistry, biology, history, geography, politics, other\n"
        "3) topic 必须是该学科下一个具体可学习的小主题（如「函数图像」「完形填空」），不要泛泛而谈\n"
        "4) reason 用第二人称「你」，聚焦客观事实，不给绝对化建议\n"
        "5) 只输出 JSON，不要 markdown 围栏，不要解释文字"
    )
    subjects_str = "、".join(f"{s['name']}（{s['minutes']}分钟）" for s in features["subjects"][:3])
    completed = features["completion"].get("completed", 0)
    abandoned = features["completion"].get("abandoned", 0)
    user_prompt = (
        f"最近 {features['recordCount']} 条学习记录，学科时长：{subjects_str or '无'}；\n"
        f"完成 {completed} 次，放弃 {abandoned} 次；\n"
        f"专注度均值 {features['focusAvg']}/5，疲劳度均值 {features['fatigueAvg']}/5；\n"
        f"活跃目标：{'、'.join(features['activeGoals']) or '无'}。\n"
        "请基于以上事实推荐一个具体可学习的主题。"
    )
    return system, user_prompt


def _extract_json_block(text: str) -> str:
    """容错：提取 markdown ```json ... ``` 围栏里的内容。"""
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text


def _fallback_recommendation(features: dict) -> dict[str, str]:
    """LLM 失败 / MockProvider 返回 None 时的兜底。"""
    subjects = features.get("subjects", [])
    if not subjects:
        return {
            "subject": "other",
            "topic": "巩固已学",
            "reason": "再多记录几次，我们会为你推荐更具体的内容",
        }
    top = subjects[0]
    return {
        "subject": top["name"],
        "topic": f"{top['name']} · 继续学习",
        "reason": f"你最近在 {top['name']} 上花了较多时间，可以继续深入",
    }


@router.get(
    "",
    response_model=RecommendationContentResponse,
    summary="导学计划页学习内容推荐（LLM 驱动）",
)
def get_recommendation_content(
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> RecommendationContentResponse:
    """数据量不足时 eligible=false（前端隐藏 LLM 推荐块）。"""
    features = _aggregate_recent_records(db, _user.user_id)

    # 阈值检查：< MIN_RECENT_RECORDS 不显示推荐
    if features["recordCount"] < MIN_RECENT_RECORDS:
        return RecommendationContentResponse.model_validate({
            "eligible": False,
            "recordCount": features["recordCount"],
            "recentWindowDays": RECENT_WINDOW_DAYS,
            "subject": None,
            "topic": None,
            "reason": f"再记录 {MIN_RECENT_RECORDS - features['recordCount']} 次学习即可获得 AI 推荐",
            "fromLLM": False,
        })

    # 阈值满足：调 LLM
    system, user_prompt = _build_prompt(features)
    text = None
    try:
        provider = get_provider()
        text = provider.generate(user_prompt, context={"system": system, "data_class": "state_plan"})
    except Exception as e:  # noqa: BLE001 — 任何 LLM 异常都降级
        logger.warning("[RECOMMEND] LLM 调用异常: %s: %s", type(e).__name__, e)

    if text:
        # 真实 LLM 可能带 ```json 围栏，先尝试原始，再尝试提取
        for candidate in (text, _extract_json_block(text)):
            try:
                data = json.loads(candidate)
                if all(k in data for k in ("subject", "topic", "reason")):
                    return RecommendationContentResponse.model_validate({
                        "eligible": True,
                        "recordCount": features["recordCount"],
                        "recentWindowDays": RECENT_WINDOW_DAYS,
                        "subject": str(data["subject"]),
                        "topic": str(data["topic"])[:50],
                        "reason": str(data["reason"])[:120],
                        "fromLLM": True,
                    })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        logger.warning("[RECOMMEND] LLM 返回格式非法: %s", text[:200])

    # 兜底
    fallback = _fallback_recommendation(features)
    return RecommendationContentResponse.model_validate({
        "eligible": True,
        "recordCount": features["recordCount"],
        "recentWindowDays": RECENT_WINDOW_DAYS,
        "subject": fallback["subject"],
        "topic": fallback["topic"],
        "reason": fallback["reason"],
        "fromLLM": False,
    })

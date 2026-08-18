"""Prompt 模板渲染测试：占位完整、用户/系统分块正确、数字字段无虚数。"""
from __future__ import annotations

import pytest

from ai_suggestion import _build_recommendation_prompt, _format_recent_records, _strip_template_controls


def test_system_user_split():
    template = open("prompts/suggestion.txt", encoding="utf-8").read()
    system, user = _strip_template_controls(template)
    # 硬约束必须在 system 部分
    for keyword in ["心理诊断", "建议联系老师", "未连接 LLM"] if False else [
        "心理诊断", "贬低", "医疗", "过度学习", "12355",
    ]:
        assert keyword in system, f"system 缺硬约束关键词: {keyword}"
    # USER 模板必须含全部占位（str.format 用 {}）
    needed = [
        "{subject}", "{stateLabel}", "{windowScore}", "{trend}",
        "{recordCount}", "{planCompletionRatio}", "{focus}", "{fatigue}",
        "{emotion}", "{difficultyFeel}", "{completion}", "{durationMinutes}",
        "{signals}", "{recentRecordsSummary}",
    ]
    for ph in needed:
        assert ph in user, f"user 模板缺占位: {ph}"


def test_render_with_full_inputs():
    rows_summary = "- 08-12 09:00 focus=4 fatigue=2 emotion=positive completion=completed"
    system, user = _build_recommendation_prompt(
        subject="math",
        state_label="fatigue_warning",
        window_score=0.42,
        trend="down",
        record_count=7,
        plan_completion_ratio=0.55,
        focus=2, fatigue=4, emotion="negative",
        difficulty_feel="hard", completion="partial", duration_minutes=45,
        signals=["自评疲劳度连续 3 次 ≥4"],
        recent_rows_summary=rows_summary,
    )
    # 占位全部填完
    for ph in ["{subject}", "{stateLabel}", "{windowScore}", "{trend}",
               "{recordCount}", "{planCompletionRatio}", "{focus}", "{fatigue}",
               "{emotion}", "{difficultyFeel}", "{completion}", "{durationMinutes}",
               "{signals}", "{recentRecordsSummary}"]:
        assert ph not in user, f"未替换的占位: {ph}"
    # 数字字段原样传入，不四舍五入到输入里没有的小数位
    assert "0.42" in user
    assert "0.55" in user
    assert "45" in user
    assert "自评疲劳度连续 3 次 ≥4" in user
    # system 仍包含硬约束关键词
    assert "心理诊断" in system
    assert "12355" in system


def test_render_with_insufficient_data():
    """数据不足时：windowScore/trend 应渲染为 null 字符串（不是数字）。"""
    system, user = _build_recommendation_prompt(
        subject="english",
        state_label="insufficient_data",
        window_score=None, trend=None, record_count=2,
        plan_completion_ratio=None,
        focus=4, fatigue=2, emotion="positive",
        difficulty_feel="moderate", completion="completed", duration_minutes=30,
        signals=[],
        recent_rows_summary="（无历史记录）",
    )
    # null 字段用 "null（…）" 显式标注，避免模型猜
    assert "null（数据不足）" in user
    assert "null（未接入计划）" in user
    assert "（无历史记录）" in user

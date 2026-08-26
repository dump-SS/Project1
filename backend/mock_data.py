"""
Mock 数据：直接复用 docs/openapi.yaml 各接口 example。

第 2 步硬编码返回这些值，等第 3 步接入 state_calculator.py / ai_suggestion.py 后，
路由里改成读取 ORM + 调 LLM。
"""
from __future__ import annotations

from schemas.assessment import AssessmentHistory, StateResultList
from schemas.goal import GoalList
from schemas.learning_record import LearningRecordList
from schemas.plan import PlanList
from schemas.recommendation import RecommendationList
from schemas.summary import SummaryList
from schemas.user import Settings, User

# --- 当前用户 ---
USER_MOCK = User.model_validate(
    {
        "userId": "u_10237",
        "stage": "senior",
        "grade": "高二",
        "subjects": ["SX", "YY", "WL"],
        "guardianAuthorization": {
            "status": "active",
            "expiresAt": "2026-09-10T00:00:00+08:00",
        },
        "onboardingCompleted": True,
    }
)

# --- 设置 ---
SETTINGS_MOCK = Settings.model_validate(
    {
        "aiWeightTuningEnabled": True,
        "sendTextToAI": False,
        "updatedAt": "2026-08-16T09:12:00+08:00",
    }
)

# --- 目标列表（含进度）---
GOAL_LIST_MOCK = GoalList.model_validate(
    {
        "items": [
            {
                "goalId": "g_5501",
                "type": "short_term",
                "subject": "SX",
                "title": "两周后期中考试数学 120+",
                "targetDate": "2026-08-30",
                "status": "active",
                "progress": {"plannedTasks": 12, "completedTasks": 7, "ratio": 0.58},
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 3},
    }
)

# --- 计划列表 ---
PLAN_LIST_MOCK = PlanList.model_validate(
    {
        "items": [
            {
                "planId": "p_9001",
                "planDate": "2026-08-16",
                "availableMinutes": 120,
                "adaptedFrom": {
                    "assessmentId": "a_7742",
                    "stateLabel": "fatigue_warning",
                    "adjustment": "reduce_load",
                    "note": "最近状态偏疲劳，本次总时长下调，单任务时长缩短并增加间隔",
                },
                "tasks": [
                    {
                        "taskId": "t_30011",
                        "subject": "SX",
                        "topic": "函数图像与性质 · 巩固已学",
                        "estimatedMinutes": 40,
                        "priority": 1,
                        "status": "pending",
                        "goalId": "g_5501",
                    }
                ],
                "createdAt": "2026-08-16T18:00:00+08:00",
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 7},
    }
)

# --- 学习记录列表 ---
LEARNING_RECORD_LIST_MOCK = LearningRecordList.model_validate(
    {
        "items": [
            {
                "recordId": "r_88012",
                "subject": "SX",
                "startedAt": "2026-08-16T19:00:00+08:00",
                "durationMinutes": 45,
                "planTaskId": "t_30011",
                "behavior": {"completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5},
                "selfReport": {"focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard"},
                "createdAt": "2026-08-16T19:46:00+08:00",
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 34},
    }
)

# --- 状态评估 ---
STATE_RESULT_LIST_MOCK = StateResultList.model_validate(
    {
        "items": [
            {
                "assessmentId": "a_7742",
                "subject": "SX",
                "windowScore": 0.48,
                "trend": "down",
                "stateLabel": "fatigue_warning",
                "displayText": "最近几次数学状态有点走低，疲劳感比较明显",
                "dataSufficient": True,
                "recordCount": 7,
                "windowSize": 7,
                "basedOn": {
                    "recordIds": ["r_88012", "r_87990", "r_87944"],
                    "signals": ["自评疲劳度连续 3 次 ≥4", "练习正确率较上周下降"],
                },
                "computedAt": "2026-08-16T19:46:00+08:00",
            },
            {
                "assessmentId": None,
                "subject": "YY",
                "stateLabel": "insufficient_data",
                "displayText": "数据积累中，再记录几次就能给出判断",
                "dataSufficient": False,
                "recordCount": 2,
                "windowSize": 7,
            },
        ]
    }
)

ASSESSMENT_HISTORY_MOCK = AssessmentHistory.model_validate(
    {
        "subject": "SX",
        "items": [
            {"date": "2026-08-14", "windowScore": 0.61, "stateLabel": "efficient_stable", "trend": "flat"},
            {"date": "2026-08-15", "windowScore": 0.55, "stateLabel": "fluctuating_up", "trend": "down"},
            {"date": "2026-08-16", "windowScore": 0.48, "stateLabel": "fatigue_warning", "trend": "down"},
        ],
    }
)

# --- 建议列表 ---
RECOMMENDATION_LIST_MOCK = RecommendationList.model_validate(
    {
        "items": [
            {
                "recommendationId": "rec_20301",
                "scene": "post_session",
                "subject": "SX",
                "generation": {
                    "status": "ready",
                    "source": "llm",
                    "completedAt": "2026-08-16T19:46:09+08:00",
                },
                "items": [
                    {
                        "title": "把单次时长压到 25 分钟",
                        "content": "这次函数练了 45 分钟但中断了 3 次，后半程正确率明显掉下来了。下次试试练 25 分钟就停，中间歇 5 分钟。",
                    }
                ],
                "basedOn": {
                    "assessmentId": "a_7742",
                    "recordId": "r_88012",
                    "stateLabel": "fatigue_warning",
                    "explain": "依据最近 7 次数学记录的疲劳自评与正确率变化",
                },
                "feedback": None,
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 12},
    }
)

# --- 复盘列表 ---
SUMMARY_LIST_MOCK = SummaryList.model_validate(
    {
        "items": [
            {
                "summaryId": "sum_4402",
                "periodStart": "2026-08-10",
                "periodEnd": "2026-08-16",
                "generation": {
                    "status": "ready",
                    "source": "llm",
                    "completedAt": "2026-08-16T22:00:12+08:00",
                },
                "content": {
                    "overview": "这周数学从「高效稳定」滑到了「疲劳预警」，主要发生在周四之后；英语记录太少，暂时看不出趋势。",
                    "patterns": [
                        "数学安排在 21 点后的 3 次记录，完成度都是部分完成，而下午的 2 次都完成了"
                    ],
                    "suggestions": [
                        "把数学挪到下午或晚饭后早一点的时段试一周",
                        "下周数学总时长先降到本周的 80%，稳住再加",
                    ],
                    "encouragement": "状态有起伏很正常，你这周把 7 次记录都填完了，这个坚持挺难得。",
                },
                "dataPoints": {
                    "recordCount": 9,
                    "subjects": ["SX", "YY"],
                    "planCompletionRatio": 0.61,
                    "referencedAssessmentIds": ["a_7742", "a_7710"],
                },
                "feedback": None,
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 4},
    }
)

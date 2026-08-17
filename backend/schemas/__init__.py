"""
Pydantic 模型集合，按 openapi.yaml 资源划分文件：

  - common.py            通用：Error / Pagination / GenerationStatus / RatingFeedback / FeedbackRecord
  - enums.py             所有枚举（Subject / Stage / StateLabel / ...）
  - user.py              用户 / 设置 / 监护人授权
  - goal.py              学习目标
  - plan.py              学习计划 + 计划任务
  - learning_record.py   学习记录（含 AssessmentSnapshot）
  - assessment.py        状态评估（StateResult / StateResultList / AssessmentHistory / ...）
  - recommendation.py    个性化建议
  - summary.py           学习总结与复盘

所有 schema 字段、必填、可空、枚举范围都严格对齐 docs/openapi.yaml。
mock 数据用 openapi.yaml 里的 example；下个 PR 接入真实计算 + LLM。
"""
from __future__ import annotations

from . import assessment, common, enums, goal, learning_record, plan, recommendation, summary, user

__all__ = [
    "common",
    "enums",
    "user",
    "goal",
    "plan",
    "learning_record",
    "assessment",
    "recommendation",
    "summary",
]

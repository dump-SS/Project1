"""
SQLAlchemy ORM 模型集合。

按 openapi.yaml 的资源划分文件，方便后续按模块 review：
  - user.py            用户 / 设置 / 监护人授权
  - goal.py            学习目标
  - plan.py            学习计划 + 计划任务
  - learning_record.py 学习记录 + 行为/自评 JSON 字段
  - assessment.py      状态评估（AssessmentSnapshot + StateResult 派生）
  - recommendation.py  个性化建议（含反馈）
  - summary.py         学习总结与复盘（含反馈）

约定：
  - id 字段统一 String(64)，由应用层生成 ID（参考 mock-server 的 _5501/_7742 风格）；
    留 nullable=False + primary_key=True。
  - 所有时间字段带 server_default=func.now()，避免业务代码漏填。
  - user_id 字段冗余存一份，方便做行级权限过滤。
"""
from __future__ import annotations

from database import Base, engine

from .assessment import AssessmentSnapshot
from .goal import Goal
from .learning_record import LearningRecord
from .plan import Plan, PlanTask
from .recommendation import Recommendation
from .summary import Summary
from .user import GuardianAuthorization, Settings, User
from .weight import UserWeightConfig, WeightAdjustLog

# 所有 ORM 类注册完成后，立即建表（幂等）。
# SQLite 开发/测试环境需要；生产迁移方案引入后可移除。
Base.metadata.create_all(bind=engine)

__all__ = [
    "User",
    "Settings",
    "GuardianAuthorization",
    "Goal",
    "Plan",
    "PlanTask",
    "LearningRecord",
    "AssessmentSnapshot",
    "Recommendation",
    "Summary",
    "UserWeightConfig",
    "WeightAdjustLog",
]

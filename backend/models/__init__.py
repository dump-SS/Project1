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

from database import Base

# auth 迁移：先把 AuthUser/AuthCode/AuthSession 注册进 Base.metadata
from auth.models import AuthCode, AuthSession, AuthUser

from .assessment import AssessmentSnapshot
from .analytics import AnalyticsEvent
from .card import CardImpression
from .chat import ChatRawMessage, ChatSession, TopicSummary, UserProfile
from .collection import Collection, CollectionItem
from .community import CommunityAggregate, CommunityAuditLog, CommunityFeature
from .exam import Exam
from .explanation import Explanation
from .goal import Goal
from .governance import ErrorReport, Medal, UsageLedger, ViolationLog
from .invite import InviteCode
from .knowledge import (
    EmbeddingRef,
    ErrorPoint,
    ErrorRecord,
    KnowledgePoint,
    KnowledgePointRelation,
    KnowledgeSubject,
    PointMastery,
    ReviewLog,
)
from .learning_record import LearningRecord
from .plan import Plan, PlanTask
from .recommendation import Recommendation
from .rate_limit import AuthRateLimit, RateLimitCounter
from .search import SearchArchive
from .summary import Summary
from .timer import TimerSegment, TimerSession
from .user import GuardianAuthorization, Settings, User
from .weight import UserWeightConfig, WeightAdjustLog
from .ai_call_log import AICallLog

# ⚠️ 这里刻意**不建表**。
#
# 历史上此处是 `Base.metadata.create_all(bind=engine)`，造成「import models 即建表」
# 的隐式副作用，两个后果：
#   1. alembic autogenerate 永远看不到差异——它 import models 时表已被建好，
#      于是对着空库也只会生成空迁移，迁移链无法自举；
#   2. 任何 import 模型的代码（包括 alembic 自身）都会隐式建表，出问题极难排查。
#
# 建表改由需要它的入口显式调用：
#   - 应用启动：main.py
#   - 测试：tests/conftest.py
#   - 独立脚本：scripts/seed_kb_math.py、scripts/import_knowledge_points.py 等

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
    "AuthUser",
    "AuthCode",
    "AuthSession",
    "KnowledgeSubject",
    "KnowledgePoint",
    "KnowledgePointRelation",
    "ErrorRecord",
    "ErrorPoint",
    "PointMastery",
    "ReviewLog",
    "EmbeddingRef",
    "AICallLog",
    "RateLimitCounter",
    "AuthRateLimit",
    "CommunityFeature",
    "CommunityAggregate",
    "CommunityAuditLog",
    # 重构 M0 新增实体（DDL 见 alembic/versions 的 M0 迁移）
    "Exam",
    "Collection",
    "CollectionItem",
    "UsageLedger",
    "InviteCode",
    "ViolationLog",
    "ErrorReport",
    "Medal",
    "UserProfile",
    "TopicSummary",
    "Explanation",
    "ChatSession",
    "ChatRawMessage",
    # M0 补漏（第二张迁移 6e7b1d2c9a04）：M2+ 的硬需求，原 11 张表未覆盖
    "TimerSession",
    "TimerSegment",
    "AnalyticsEvent",
    "SearchArchive",
    "CardImpression",
]

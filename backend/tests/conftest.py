"""测试套件全局夹具：默认强制 MockProvider，隔离真实 LLM；DB 每用例清空。

原因：
1. LLM 隔离——test_routes_engine / test_ai_suggestion 等用例断言的是引擎与状态机
   行为（快、确定性）。若开发机 .env 配了真实 LLM_API_KEY，这些用例会真实
   调用供应商——每次 10-30 秒、可能超时、且 source 断言会因兜底而随机失败。
2. DB 隔离——阶段 3 接 DB 后，plan/goal/learning-record 等真落库；
   若不清表，跨用例/跨运行的同 planDate、同 subject 数据会污染冷启动与趋势断言。

规则：
- `pytest tests/`                     → 全部走 Mock（快、确定、零成本），DB 每用例清空
- `REAL_LLM=1 pytest tests/test_real_llm.py` → 放行真实 LLM（只跑该文件）

实现：pydantic-settings 优先级是 环境变量 > .env 文件，conftest 在所有
测试模块 import config 之前执行，所以在 os.environ 层覆盖即可。
"""

from __future__ import annotations

import os

import pytest

if not os.environ.get("REAL_LLM"):
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["LLM_API_KEY"] = ""


@pytest.fixture(autouse=True)
def _reset_db():
    """每个测试用例前清空所有业务表，保证用例间数据隔离。

    阶段 3 后 plan/goal/learning-record 等真落库；若不清表，跨用例的同 planDate
    会触发 409，跨用例的同 subject 数据会污染冷启动与趋势断言。
    在 app lifespan 建表后清表，保留 schema。
    """
    # 延迟 import，确保 conftest 顶部的环境变量覆盖先生效
    from database import engine
    from models import Base  # noqa: F401（触发 ORM 注册）

    # 确保表结构存在（首次运行或 data.db 被删时）
    Base.metadata.create_all(bind=engine)

    # 清空所有表数据，保留 schema
    with engine.connect() as conn:
        # 按依赖反序删除（plan_tasks 依赖 plans 等）
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

    yield

    # 用例结束后无需额外清理（下个用例的开头会清）

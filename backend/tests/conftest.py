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

    升级：开发机已有的 data.db 可能比当前 models 字段少（之前 create_all 是 IF NOT EXISTS，
    不会 ALTER），所以首次启动时检测到 metadata 缺失列就 drop_all + create_all 重建。
    """
    # 延迟 import，确保 conftest 顶部的环境变量覆盖先生效
    from sqlalchemy import inspect

    from database import engine
    from models import Base  # noqa: F401（触发 ORM 注册）

    # 检测 schema 是否包含最新字段（避免老 DB 文件缺列导致运行时 AttributeError）。
    # data_plan_completed_count 是 2026-08-18 新增的字段，作为「是否需要重建」的探针。
    insp = inspect(engine)
    if insp.has_table("summaries"):
        cols = {c["name"] for c in insp.get_columns("summaries")}
        if "data_plan_completed_count" not in cols:
            # 老 DB，重建
            Base.metadata.drop_all(bind=engine)
    # 板块二 v2.2：goals.point_ids 也是新列，老库需重建
    if insp.has_table("goals"):
        cols = {c["name"] for c in insp.get_columns("goals")}
        if "point_ids" not in cols:
            Base.metadata.drop_all(bind=engine)
    # S0-T6：user_weight_configs.m1 内容权重列，老库需重建
    if insp.has_table("user_weight_configs"):
        cols = {c["name"] for c in insp.get_columns("user_weight_configs")}
        if "m1" not in cols:
            Base.metadata.drop_all(bind=engine)
    # S0-T6（写入侧）：weight_adjust_logs.before_m1 留痕快照列，老库需重建
    if insp.has_table("weight_adjust_logs"):
        cols = {c["name"] for c in insp.get_columns("weight_adjust_logs")}
        if "before_m1" not in cols:
            Base.metadata.drop_all(bind=engine)
    # 知识点库建表：kb_points.explanation 内容列，老库需重建
    if insp.has_table("kb_points"):
        cols = {c["name"] for c in insp.get_columns("kb_points")}
        if "explanation" not in cols:
            Base.metadata.drop_all(bind=engine)

    # 确保表结构存在
    Base.metadata.create_all(bind=engine)

    # 清空所有表数据，保留 schema
    with engine.connect() as conn:
        # 按依赖反序删除（plan_tasks 依赖 plans 等）
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

    yield

    # 用例结束后无需额外清理（下个用例的开头会清）

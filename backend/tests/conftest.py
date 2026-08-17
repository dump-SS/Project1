"""测试套件全局夹具：默认强制 MockProvider，隔离真实 LLM。

原因：test_routes_engine / test_ai_suggestion 等用例断言的是引擎与状态机
行为（快、确定性）。若开发机 .env 配了真实 LLM_API_KEY，这些用例会真实
调用供应商——每次 10-30 秒、可能超时、且 source 断言会因兜底而随机失败。

规则：
- `pytest tests/`                     → 全部走 Mock（快、确定、零成本）
- `REAL_LLM=1 pytest tests/test_real_llm.py` → 放行真实 LLM（只跑该文件）

实现：pydantic-settings 优先级是 环境变量 > .env 文件，conftest 在所有
测试模块 import config 之前执行，所以在 os.environ 层覆盖即可。
"""

from __future__ import annotations

import os

if not os.environ.get("REAL_LLM"):
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["LLM_API_KEY"] = ""

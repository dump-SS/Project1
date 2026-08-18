# EpochX API 后端

FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite，严格按 [`docs/openapi.yaml`](../docs/openapi.yaml) 实施。

## 当前阶段

**阶段 3（进行中）：状态量化 + 建议状态机已接入真实引擎**

- ✅ **状态计算已接引擎**：`POST /learning-records`、`DELETE /learning-records/{id}`、
  `GET /assessments/current`、`GET /assessments` 全部落库并调
  [`state_engine`](state_engine/) 真实计算，不再返回 mock 常量。
  接入点是 [`state_calculator.py`](state_calculator.py)——即 main.py 注释里预留的那个模块。
- ✅ **建议生成链路已接入**：提交学习记录会真实插入 Recommendation pending 行，
  再经 [`ai_suggestion.py`](ai_suggestion.py) 生成并写回；默认 MockProvider 走规则模板兜底，
  前端轮询同一个 recommendationId 可拿到 `ready + source=template`。
- ⏳ **复盘状态机已接入，真实 LLM 待配置**：记录不足时返回 `insufficient_data`；
  MockProvider/真实 LLM 失败时严格返回 `failed`，不伪造 `template`（PRD 5.4）。
- ⏳ 其余资源路由（goal / plan / user）仍读 [mock_data.py](mock_data.py)。

计算分层（PRD 6.1 铁律：模型负责表达，规则负责事实）：

```
routes/*.py               HTTP 层：校验、落库、组装响应
  └─ state_calculator.py  编排：ORM ↔ 引擎输入 ↔ 契约 dict
       └─ state_engine/   纯计算：公式、趋势、标签、权重校验（零外部依赖）
```

## 快速开始

> **Python 版本**：需 3.11+，推荐 **3.12**（见 `.python-version`）。
> Python 3.14 上 `pydantic==2.10.3` 没有预编译 wheel、需本地编译，装不上。

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # macOS / Linux

# 2. 装依赖（依赖声明统一在 pyproject.toml，已无 requirements.txt）
pip install -e ".[dev]"
# 若 setuptools 报 "Multiple top-level packages"，直接装依赖列表亦可：
# pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy "passlib[bcrypt]" python-dotenv httpx pytest

# 3. 配 .env
cp .env.example .env
# 按需修改 DATABASE_URL / JWT_SECRET / LLM_*

# 4. 启动
uvicorn main:app --reload --port 8000
```

打开 <http://localhost:8000/docs> 看 Swagger UI，所有 29 个接口都能 `Try it out`。

## 项目结构

```
backend/
├── main.py                  FastAPI app + lifespan + 统一错误处理
├── config.py                pydantic-settings 读 .env
├── database.py              SQLAlchemy 2.0 + SessionLocal + get_db
├── middleware.py            请求 ID + 访问日志
├── mock_data.py             阶段 2 的硬编码假数据（直接复用 openapi.yaml example）
├── models/                  SQLAlchemy ORM 模型（9 张表）
│   ├── user.py              User / Settings / GuardianAuthorization
│   ├── goal.py              Goal
│   ├── plan.py              Plan / PlanTask
│   ├── learning_record.py   LearningRecord
│   ├── assessment.py        AssessmentSnapshot
│   ├── recommendation.py    Recommendation
│   └── summary.py           Summary
├── schemas/                 Pydantic v2 模型（50+ schema，严格对齐 openapi.yaml）
│   ├── enums.py             Subject / StateLabel / ...
│   ├── common.py            Error / Pagination / GenerationStatus / RatingFeedback
│   ├── user.py              User / UserProfilePut / Settings / SettingsUpdate / GuardianAuthorizationRequest
│   ├── goal.py              Goal / GoalCreate / GoalList ...
│   ├── plan.py              Plan / PlanTask ...
│   ├── learning_record.py   LearningRecord / RecordInput / ...
│   ├── assessment.py        StateResult / AssessmentHistory
│   ├── recommendation.py    Recommendation / RecommendationCreate
│   └── summary.py           Summary / SummaryContent
├── routes/                  FastAPI 路由（按 openapi.yaml 7 个 tag）
│   ├── health.py            /health（带 DB 探活）
│   ├── user.py              /me, /me/settings, /me/guardian-authorization
│   ├── goal.py              /goals
│   ├── plan.py              /plans
│   ├── learning_record.py   /learning-records
│   ├── assessment.py        /assessments
│   ├── recommendation.py    /recommendations（ORM + ai_suggestion）
│   └── summary.py           /summaries（ORM + ai_suggestion）
├── state_calculator.py      编排层：ORM ↔ 引擎输入 ↔ 契约 dict（阶段 3 接入点）
├── ai_suggestion.py         AI 编排：provider → 安全审核 → 兜底/失败 → ORM
├── llm_provider.py          供应商抽象：MockProvider / OpenAICompatibleProvider
├── template_fallback.py     规则模板兜底（PRD 5.3）
├── safety_filter.py         内容安全审核 hook（PRD 6.3）
├── state_engine/            纯计算引擎（零外部依赖，PRD 5.2）
│   ├── types.py             引擎数据类型 + 权重配置 + 标签阈值
│   ├── scoring.py           单次状态分（PRD 5.2§1 公式）
│   ├── assessment.py        滑动窗口趋势 + 标签判定（PRD 5.2§2-3）
│   ├── weights.py           AI 调权硬限制校验（PRD 5.2§4）
│   └── adapter.py           契约 camelCase JSON ↔ 引擎类型
├── tests/
│   ├── test_smoke.py        烟雾测试：import / schema 校验 / 路由响应 / 错误格式
│   ├── test_routes_engine.py 路由 ↔ 引擎集成测试（真实计算而非 mock）
│   ├── test_scoring.py      单次评分单测
│   ├── test_assessment.py   趋势与标签单测
│   ├── test_weights.py      调权校验单测
│   └── test_adapter.py      适配层单测
├── pyproject.toml           依赖 + pytest 配置（统一入口，已合并原 requirements.txt / pytest.ini）
├── .python-version          给 uv / pyenv 用的
├── .env.example
└── README.md
```

## 关键约定

### 字段名：snake_case（Python） ↔ camelCase（JSON）

Pydantic v2 的 `alias` 只对**反序列化**生效，序列化默认用字段名。统一在 [main.py](main.py) 顶层开 `response_model_by_alias=True`，所有响应**默认输出 camelCase**，与 openapi.yaml 对齐。

需要加新字段时**同时**加 `alias` + `populate_by_name=True`：

```python
class Foo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    my_field: int = Field(..., alias="myField", description="...")
```

### 错误响应：统一格式

所有非 2xx 都返回 `docs/openapi.yaml` 0.2 节定义的格式：

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "请求参数校验失败",
    "field": "selfReport.focus"
  }
}
```

- 400 → `VALIDATION_FAILED`（Pydantic 校验失败）
- 401 → `UNAUTHENTICATED`
- 403 → `GUARDIAN_AUTHORIZATION_EXPIRED`
- 404 → `RESOURCE_NOT_FOUND`
- 409 → `STATE_CONFLICT`
- 429 → `RATE_LIMITED`

### 请求 ID

每个请求会自动生成 `X-Request-ID`（或透传客户端传入的），写入响应头和访问日志，方便排查问题：

```
[4f8a2c1e9b3d4a7f] GET /me → 200 (1.2ms)
[4f8a2c1e9b3d4a7f] POST /learning-records → 201 (45.3ms)
```

## 跑测试

```bash
pytest                    # 跑全部
pytest tests/test_smoke.py::test_mock_data_validates -v   # 单个用例
```

20 个测试覆盖：
- 启动 + 导入
- 枚举值与 openapi.yaml 一致性
- mock 数据能通过 schema 校验
- 响应字段名是 camelCase
- SettingsUpdate 至少一项校验
- GuardianAuthorizationRequest 二选一校验
- RecordInput 字段范围（focus / durationMinutes）
- 关键接口（GET /me / GET /goals / POST /learning-records）的真实响应
- 统一错误响应格式
- 5 个分页列表接口都带 items + pageSize

## 下一步要做

- [x] 接入 `state_calculator.py` 替换 `routes/learning_record.py` 里的 mock 重算
- [x] 接入 `ai_suggestion.py` 替换 `routes/recommendation.py` + `routes/summary.py` 的 mock；
      默认 MockProvider 验证模板兜底，真实 LLM 等 `.env` 配置 API key / base_url / model
- [x] 真实 LLM 已验证（aiping.cn / Step-3.5-Flash，OpenAI 兼容 Bearer）：
      端到端 source=llm 通过；超时 60s + 1 次重试 + 异常全兜底（超时/解析失败走模板，绝不 500）
- [x] 异步生成（PRD 6.4）：三条 POST 路由改 BackgroundTasks，立即返回 pending 句柄；
      实测 POST 从最坏 ~2min 降到 ~2s，LLM 在后台自开 session 完成并写终态，前端轮询读取
- [ ] 进程内并发上限 / 任务队列：BackgroundTasks 在单进程内跑，高并发下需要队列（Celery/RQ）+ 去重
- [ ] AICallLog 持久化：当前用 logging 留痕，PRD 6.5 的正式调用记录表待建
- [ ] 真实速率限制（PRD 6.4）：config 有建议 5/天、复盘 1/天配额，尚未计数/返回 429
- [ ] **给 `learning_records` 加自增序列列**：当前窗口排序用
      `(started_at, created_at, id)`，保证了确定性；但同一秒内批量插入且
      `started_at` 相同时，无法还原真实插入顺序（趋势斜率可能与实际录入次序不符）。
      彻底解决需要一个单调递增序列列。
- [ ] JWT 解析替换 `routes/deps.py` 里的 `current_user` 占位
- [ ] 真实速率限制（PRD 6.4）
- [ ] Alembic 迁移（当前 `Base.metadata.create_all` 够 MVP 阶段）
- [ ] 集成测试（用 `httpx.AsyncClient` 真发 HTTP）

# EpochX API 后端

FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite，严格按 [`docs/openapi.yaml`](../docs/openapi.yaml) 实施。

## 当前阶段

**阶段 2：Pydantic schemas + 路由 + mock 数据**

所有 29 个接口都在 `/docs` 可发请求，返回 [mock_data.py](mock_data.py) 里硬编码的假数据。等拿到 `state_calculator.py` + `ai_suggestion.py` 后，开第 3 步 PR 替换 mock。

## 快速开始

```bash
# 1. 创建虚拟环境（推荐 3.12，详见 .python-version）
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # macOS / Linux

# 2. 装依赖
pip install -r requirements.txt

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
│   ├── recommendation.py    /recommendations
│   └── summary.py           /summaries
├── tests/
│   └── test_smoke.py        20 个烟雾测试：import / schema 校验 / 路由响应 / 错误格式
├── requirements.txt
├── pytest.ini
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

- [ ] 接入 `state_calculator.py` 替换 `routes/learning_record.py` 里的 mock 重算
- [ ] 接入 `ai_suggestion.py` 替换 `routes/recommendation.py` + `routes/summary.py` 里的 mock
- [ ] JWT 解析替换 `routes/deps.py` 里的 `current_user` 占位
- [ ] 真实速率限制（PRD 6.4）
- [ ] Alembic 迁移（当前 `Base.metadata.create_all` 够 MVP 阶段）
- [ ] 集成测试（用 `httpx.AsyncClient` 真发 HTTP）

# EpochX API 后端

FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite（本地开发）/ Postgres（Neon，目标环境），严格按 [`docs/openapi.yaml`](../docs/openapi.yaml) 实施。

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

打开 <http://localhost:8000/docs> 看 Swagger UI，所有接口都能 `Try it out`。

## 项目结构

```
backend/
├── main.py                  FastAPI app + lifespan + 统一错误处理
├── config.py                pydantic-settings 读 .env
├── database.py              SQLAlchemy 2.0 + SessionLocal + get_db
├── middleware.py            请求 ID + 访问日志
├── mock_data.py             阶段 2 的硬编码假数据（直接复用 openapi.yaml example）
├── models/                  SQLAlchemy ORM 模型（47 张表）
│   ├── user.py              User / Settings / GuardianAuthorization
│   ├── goal.py              Goal
│   ├── plan.py              Plan / PlanTask
│   ├── learning_record.py   LearningRecord
│   ├── assessment.py        AssessmentSnapshot
│   ├── recommendation.py    Recommendation
│   └── summary.py           Summary
├── schemas/                 Pydantic v2 模型（17 个文件，契约 174 schema，严格对齐 openapi.yaml v1.7.1）
│   ├── enums.py             Subject / StateLabel / ...
│   ├── common.py            Error / Pagination / GenerationStatus / RatingFeedback
│   ├── user.py              User / UserProfilePut / Settings / SettingsUpdate / GuardianAuthorizationRequest
│   ├── goal.py              Goal / GoalCreate / GoalList ...
│   ├── plan.py              Plan / PlanTask ...
│   ├── learning_record.py   LearningRecord / RecordInput / ...
│   ├── assessment.py        StateResult / AssessmentHistory
│   ├── recommendation.py    Recommendation / RecommendationCreate
│   └── summary.py           Summary / SummaryContent
├── routes/                  FastAPI 路由（22 个文件 / 20 个 router，契约 64 paths / 84 operations / 16 个 tag）
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

50 个测试文件 / 383 个用例（2026-09-27 实测 `pytest --collect-only`；上一版 README 写「20 个测试」已过期）。基础冒烟（`test_smoke.py`）覆盖：
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

其余按域分布（挑几个有代表性的）：
- **契约一致性**：`test_e2e_contract.py`（最大，54 例）、`test_openapi_contract.py`
- **身份与安全**：`test_auth.py`(40)、`test_auth_strict_mode.py`（专测 `allow_insecure_user_header=false` 的生产口径）、`test_me_and_guardian.py`(28)、`test_auth_rate_limit.py`
- **合规**：`test_egress_ci.py` / `test_community_egress_ci.py`（出域 CI 断言）、`test_egress_guard.py`、`test_privacy_filter.py`(26)
- **状态引擎**：`test_scoring.py`、`test_adapter.py`、`test_self_report_optional.py`（自评四字段全可空，且齐全时逐字节对齐旧公式）、`test_record_writeback.py`
- **M2 交付**：`test_timer_session.py`(36)、`test_exam.py`、`test_exam_record_linkage.py`（D49 成绩回填）、`test_goal_tree.py`
- **计量与治理**：`test_usage_ledger.py`、`test_ai_call_log.py`、`test_rate_limit.py`、`test_violation.py`
- **知识与向量**：`test_embedding_service.py`、`test_vector_store.py`、`test_rag_retrieval.py`、`test_knowledge_kb.py`、`test_mastery_engine.py`

> ⚠️ 测试库隔离在 `backend/.pytest_data/test.db`（**故意用子目录**，避免 `vector_store` 的索引路径
> 指向真实 `kb_vectors/`），`LLM_PROVIDER=mock` 强制。改 `conftest.py` 前先读 `README.md` 待办里
> 2026-09-15 那条事故记录。

## 下一步要做

### ✅ 已修：2026-09-27 一次性收口三项实测发现

三项都已改完并有测试/实测背书，**未改动 `docs/openapi.yaml`**（见下方「为什么没动契约」）。

**1. 🔴 错题原文出域到外部 embedding API（合规红线 · 契约漂移）**

- 现象：`embedding_service.embed_text()` 是单一全局函数、只读全局 `KB_EMBED_MODE`、
  **不区分调用来源**，且**完全不过 `egress_guard`**（该模块此前只出现在 `llm_provider.py` 与测试里）。
  于是 `.env` 里 `KB_EMBED_MODE=api` + 智谱 `EMBED_BASE_URL` 时，
  `routes/error_book.py` 与 `routes/knowledge.py`（`/error-parse` 路径 2）会把**错题原文发出去**。
  `tests/test_rag_retrieval.py` 当时还把 `embed_mode="api"` 设成错题召回的**成功路径**，等于把违规固化成了预期行为。
- 修法：
  - `egress_guard.py` 新增 `EMBED_SRC_KB` / `EMBED_SRC_USER` 与 `assert_embed_source_offdomain_allowed()`，
    沿用该模块既有的「默认拒绝」风格（未声明来源 = 越权）。
  - `embedding_service.py` 的 `embed_text(text, *, source=...)` 与新函数 `embed_mode_for(source)`：
    **用户内容恒定解析为 `local`，不看 `KB_EMBED_MODE`**，且不提供任何配置开关去放开。
    判定不通过时退回 local，local 再失败返回 `None`（**宁缺毋滥、不造数**，D34）。
  - 错题两处调用点显式传 `source=EMBED_SRC_USER`，并把**实际使用的模式**写进 `kb_embeddings.model`
    （旧代码记的是全局配置值，会记错）。
  - 知识库链路（`routes/knowledge_kb.py` 的 `/knowledge/points/match`）**保持** `EMBED_SRC_KB` 不变。
- 测试：`tests/test_embedding_service.py` +6 例（含「api 模式下用户内容绝不调 `_embed_api`」，
  把 `_embed_api` 换成炸弹）；`tests/test_rag_retrieval.py` 4 处断言由 `api` 翻转为 `local` +2 例。
  `tests/test_egress_ci.py` 新增**AST 静态扫描**：除知识库链路外，任何 `embed_text` 调用点漏标 `source`
  直接挂 CI（已用 tamper 测试验证过真能抓到，报到行号）。

**2. `main.py` 静态托管指向源码目录 → 「单端口生产形态」实际是白屏**

- 现象：`FRONTEND_DIR` 默认取 `frontend/`（源码），而 `frontend/index.html` 引用 `/src/main.jsx`。
  catch-all 会把 JSX 当普通 JS 吐出去，浏览器解析失败**白屏**；`/brand/*`、`/bg-sky.jpg`
  这些 `public/` 资源也会 404（它们构建时才复制到 `dist/` 根）。
- 修法：默认改指 `frontend/dist`；产物缺失时返回带 `npm run build` 指引的 404 JSON，
  **不**回退去服务源码。目录穿越防护（`is_relative_to`）保持不变。
- 实测（起真实服务打真实请求，非推断）：`/` 200 HTML、`/goals` `/personal-data` 走 SPA 回退 200、
  `/assets/index-*.js` 200 且 MIME 正确、`/brand/*.png` 200、`/health` 与 `/api/v1/*` 未被 catch-all 截走
  （后者走到真路由返 401）、三次目录穿越尝试均未泄露源码。
- 顺带把文件头「阶段 3 接入 state_calculator / ai_suggestion（待）」这段过期描述改成了现状。

**3. `usage_ledger` 计价表空心**

- 现象：`MODEL_PRICING = {}`，所有模型都按 `FALLBACK_PRICING=(2.0, 8.0)` 计，成本数值看着可信但其实是兜底价。
- 修法：新增 `USAGE_MODEL_PRICING` 环境变量（`"模型=输入元,输出元;..."`，单位 元/1M tokens），
  运营核定单价后**只改环境变量、不用改代码**；新增 `resolve_pricing()` 返回 `(入价, 出价, 是否兜底)`，
  把「这是兜底价」显式暴露；兜底时按模型名去重告警一次。
- **刻意没写死任何真实单价**——单价属运营口径，编一个占位数会把「数值成本」变成看起来可信的假数据。
  当前实际只会打到 `LLM_MODEL` 那一个模型，填表成本很低。
  格式错误的条目跳过并告警，不会让整张表解析失败；解析结果按 spec 缓存，不刷屏。

**为什么没动契约**：这三项全是**内部实现**修正，不新增/不删除任何 path、operation、schema 或字段。
其中第 1 项尤其不是设计决策——`openapi.yaml` 早已写明「错题录入（原文只在本地 embedding，永不出域）」、
「embedding 走本地模型，PRD 12.6」、「向量库/embedding 未就绪时降级为名称关键词模糊匹配（**接口形态不变**）」，
代码是**违反了既有契约**；本次改动是把代码拉回契约，降级口径也与契约一致。
所以 `openapi.yaml` 保持 **v1.7.1** 不变。

---

- [x] 接入 `state_calculator.py` 替换 `routes/learning_record.py` 里的 mock 重算
- [x] 接入 `ai_suggestion.py` 替换 `routes/recommendation.py` + `routes/summary.py` 的 mock；
      默认 MockProvider 验证模板兜底，真实 LLM 等 `.env` 配置 API key / base_url / model
- [x] 真实 LLM 已验证（aiping.cn / Step-3.5-Flash，OpenAI 兼容 Bearer）：
      端到端 source=llm 通过；超时 60s + 1 次重试 + 异常全兜底（超时/解析失败走模板，绝不 500）
- [x] 异步生成（PRD 6.4）：三条 POST 路由改 BackgroundTasks，立即返回 pending 句柄；
      实测 POST 从最坏 ~2min 降到 ~2s，LLM 在后台自开 session 完成并写终态，前端轮询读取
- [ ] 进程内并发上限 / 任务队列：BackgroundTasks 在单进程内跑，高并发下需要队列（Celery/RQ）+ 去重
- [x] AICallLog 持久化（PRD 6.5）：表 `ai_call_logs` 在基线迁移 `1a6f0c6bb285` 已建；写入器 `ai_call_log.py`
      挂在 `llm_provider.generate` 的 4 个出口（mock 无输出 / 成功 / 失败 / 出域拦截）。**表刻意不带身份字段**，
      回归见 `tests/test_ai_call_log.py`（含「不得存用户身份」列级断言）。
- [x] 真实速率限制（PRD 6.4）：`rate_limit_counters` 表 + `auth/rate_limit.py`（IP/邮箱维度 + 失败锁定）已实现。
      业务配额在各自路由内计数：建议 5/天、复盘 1/天、`POST /knowledge-summary`。回归见 `tests/test_rate_limit.py`、
      `tests/test_auth_rate_limit.py`。**注意进程内计数，多实例部署需换共享存储。**
- [ ] **给 `learning_records` 加自增序列列**：当前窗口排序用
      `(started_at, created_at, id)`，保证了确定性；但同一秒内批量插入且
      `started_at` 相同时，无法还原真实插入顺序（趋势斜率可能与实际录入次序不符）。
      彻底解决需要一个单调递增序列列。
- [ ] JWT 解析替换 `routes/deps.py` 里的 `current_user` 占位——⚠️ 现役认证是**不透明 `sid` cookie**
      → SHA-256 → `auth_sessions` 查表，JWT 已声明但**未接线**。加 JWT 前先确认是否真要双轨。
- [x] Alembic 迁移定位（2026-09-15 **squash 后反转**）：**Alembic 是 schema 唯一真相源**，空库建表走 `alembic upgrade head`，upgrade / downgrade 可反复执行。基线 `1a6f0c6bb285` 是 autogenerate 产出的显式 DDL（29 张表），不再引用 `Base.metadata`。
      - 历史：2026-08-31 的旧决议是"`create_all` 为唯一真相源、勿运行 `upgrade head`"，原因是原基线 `ee1d7e6e893c` 用 `Base.metadata.create_all` 建出**全部**表，导致后续增量迁移全部冲突——整条链无法从空库跑通。那 14 个 revision 已归档到 `alembic/versions_archive/`（不参与扫描）。
      - 同时移除了 `models/__init__.py` 里「import 即建表」的副作用（它会让 autogenerate 永远看不到差异）。`create_all` 现仅保留在 `main.py`（应用启动）与 `tests/conftest.py`（测试重建）。
      - 新增模型/列：改 ORM 模型 → `alembic revision --autogenerate -m "..."` → **人工 review 产物**（server_default / 索引命名未必还原到位）→ 提交。详见 `alembic/env.py` 顶部说明。
- [x] **M0 迁移（2026-09-19，重构契约冻结）**：`5015e9b1bdeb`，`down_revision = 1a6f0c6bb285`，**单 head**。
      - 内容：稳定用户 ID 改造（users 加 email/handle、auth_users 加 user_id、**auth_sessions 由存 email 改存 user_id**）；13 张新表（exams / collections / collection_items / usage_ledger / invite_codes / violation_logs / error_reports / medals / user_profiles / topic_summaries / explanations / chat_sessions / chat_raw_messages）；goals 加 parent_goal_id + exam_id + target_score；kb_errors 加 error_cause + intent + source_exam_id。表数 29 → **42**。
      - ⚠️ `auth_sessions` 是**重建表**（不是 add/drop column）：在已有数据上加 NOT NULL 列没有可用默认值，且 SQLite 的 DROP COLUMN 支持有限。会话是 7 天 TTL 的临时数据，pilot 删档期直接重建——**升级后所有人需重新登录一次**。
      - ⚠️ **Postgres 方言修复**：`auth_sessions.expires_at` / `auth_codes.expires_at` 存的是毫秒时间戳（约 1.7e12），原为 `Integer` 会超出 int32 上限。SQLite 的 INTEGER 是动态宽度所以本地一直没暴露，**Neon 上会直接溢出报错**——本次一并改为 `BigInteger`。
      - ⚠️ **依赖补缺**：`pyproject.toml` 此前**没有任何 Postgres 驱动**，DATABASE_URL 指向 Neon 时会直接报 `No module named 'psycopg2'`。已补 `psycopg2-binary`。
      - 验证：空库 `upgrade head` 在 **SQLite 与 Neon Postgres 各跑通一次**；`downgrade` 可回退；对迁移后的空库跑 `alembic check` 报 "No new upgrade operations detected"（迁移产物与 ORM 元数据一致）。
      - 学科数据：`kb_subjects` 此前 **0 行**（导致 `GET /knowledge/subjects` 必返空），已由 `scripts/seed_kb_subjects.py` 补 9 行（幂等），本地库与 Neon 均已导入。
- [x] **M0 补漏迁移（2026-09-19 同日）**：`b81d83bafb89`，`down_revision = 5015e9b1bdeb`，**单 head**。
      - 原 11 张表未覆盖 M2+ 的硬需求，补齐 5 张：`timer_sessions` + `timer_segments`（C·§3.6/D30/D31/#14 服务端持久化计时会话与分段）、`analytics_events`（G·D39 三块埋点）、`search_archives`（D·§3.8.4 搜题归档，与讲解归档分开）、`card_impressions`（E·D28 推荐卡冷却与去重指纹）。表数 42 → **47**。
      - 全部是新建表（无 ALTER），故无 SQLite 方言问题；`upgrade` / `downgrade` / `alembic check` 均已验证，SQLite 与 Neon 同步升级。
- [x] **C 板块迁移**：`c7a1f2e4d9b3`，`down_revision = b81d83bafb89`，**单 head**。自评四列可空化 +
      `learning_records.source` / `source_exam_id` + `exams.duration_minutes`（变更单见
      `docs/refactor-c-handoff-to-x0.md`）。
- [ ] ⚠️ **本地 `data.db` 落后于 head 是常见现象，pytest 抓不到**（2026-09-27 实际发生过一次）：
      拉了新代码后本地库还停在旧 revision，代码已在读新列 → 相关接口 `no such column`，
      但 `pytest` 仍全绿——因为 `tests/conftest.py` 把 `DATABASE_URL` 强制到独立的
      `backend/.pytest_data/test.db` 且用 `create_all` 从模型重建，与开发库无关。
      **症状：本地某条业务链 500，但测试全绿。**
      确认手段：`alembic check` 报 `Target database is not up to date`。
      修法：`alembic upgrade head`（**纯增量、非破坏**；先备份 `data.db`，
      `.gitignore` 已有 `*.db.bak*` 规则）。涉及共享开发库时先知会 X0——铁律 2 约束的是
      **写新迁移**，不是应用已合入的迁移。
- [ ] 集成测试（用 `httpx.AsyncClient` 真发 HTTP）

# 部署栈评估（pilot 上线技术选型）

> 版本：v1.0 · 2026-09-15  
> 范围：**只评估选型合理性与落地风险**，不含逐步部署手册。  
> 前提：合规部分已由团队完成评估，本文**不做合规判断**。  
> 阶段口径：pilot（小范围试用验证）——本文所有建议以"最省事、最少故障点"为准，不为规模做过度设计。  
> 关联：[product-redesign-target.md](./product-redesign-target.md)（产品目标态）· [refactor-2026-09-feature-ia-logic.md](./refactor-2026-09-feature-ia-logic.md)（现状基线）
>
> **状态说明（2026-09-18 补记）**：§4 清单中 P0 越权修复、P1 Alembic 空库自举、P1 CORS 白名单、P1 Cookie Secure/SameSite、P2 auth 限流持久化**已全部完成**（2026-09-15，HEAD `736461a`，勿再当待办派发）。**剩余待办**：P0 后端平台选型定稿、P2 密钥迁入平台 Secrets、P3 R2。§5 支付选型段落的 MoR 推荐已被 #30（需支持支付宝+微信+海外）修正，且支付整体**推迟到 pilot 测试结束后**——该节仅作背景，以 [pending-decisions.md](./pending-decisions.md) 为准。附 A / 附 B 两张任务单均已执行完毕，保留作修复档案。

---

## 0. 结论先行

| 组件                          | 结论              | 一句话理由                                     |
| --------------------------- | --------------- | ----------------------------------------- |
| Cloudflare（DNS + CDN + SSL） | ✅ 采用            | 免费、成熟                                     |
| **Vercel（前端）**              | ✅ 采用            | Vite 静态产物，正是它的主场                          |
| **Vercel（后端）**              | ❌ **不建议**       | FastAPI 在 Serverless 上会有 4 处**静默失效**，见 §2 |
| **后端托管**                    | 🔄 **换成常驻容器平台** | Railway / Fly.io / Render 任一              |
| Neon（Postgres）              | ✅ 采用            | 免费层 + 数据库分支，pilot 阶段开 staging 分支很值        |
| SQLAlchemy + Alembic        | ✅ 采用            | 已有；⚠️ 但"alembic 只留痕"的决策**必须反转**，见 §2-4    |
| Pydantic                    | ✅ 已有            | —                                         |
| FastAPI-Users               | ❌ **不建议引入**     | 会重写认证层，且不管 14 岁以下 / 监护人授权分支，见 §1-3        |
| Resend                      | ✅ 采用            | 现状已有 `smtp_provider=real/mock` 双模，替换成本极低  |
| Cloudflare R2               | 🟡 保留但后置        | **目前全仓无上传路由**，无消费者，等真的有图片上传再启用            |

---

## 1. 拟选栈逐项评估

### 1.1 为什么后端不该放 Vercel

不是"能不能跑"的问题（技术上能跑，通过 ASGI adapter），而是**跑起来会有四处悄悄坏掉**——不是报错，是**静默失效**，比报错更难查：

1. 常驻定时任务不执行；
2. 限流与失败锁定计数失效；
3. 向量索引读不到；
4. 冷启动每次加载 26.5MB 索引。

详见 §2。

### 1.2 后端平台怎么选

三个候选都能满足需求，**差别不在能力而在运维心智负担**：

| 平台          | 特点                         | 适配度         |
| ----------- | -------------------------- | ----------- |
| **Railway** | 一个服务 + Postgres 插件即可跑；配置最少 | pilot 阶段最省事 |
| **Fly.io**  | 全球边缘部署、常驻 VM；配置略多          | 需要地域优化时选它   |
| **Render**  | 有免费层（会冷启动）；配置简单            | 预算极紧时可考虑    |

> ⚠️ 若选自带 Postgres 的平台，**Neon 仍可保留**（团队已决定一步到位）：用它做 staging 分支 / 数据分析副本，生产库也可直接用它。接 Neon 时注意连接池（`pool_pre_ping=True`）。

### 1.3 为什么不引入 FastAPI-Users

| 现状已有                                       | FastAPI-Users 能给    |
| ------------------------------------------ | ------------------- |
| 10 个 `/auth/*` 接口全在 FastAPI                | 注册 / 登录 / 改密 / 邮箱验证 |
| `AuthUser` / `AuthCode` / `AuthSession` 三表 | （同左，但表结构不同）         |
| HttpOnly cookie session（`auth/session.py`） | 默认形态是 **JWT**       |
| 14 岁以下独立规则 + 监护人授权分支                       | ❌ 不管                |

**结论**：它提供的能力你们全都有，换它等于**重写认证层去换一个不覆盖你们核心合规分支的方案**。

**关于"接支付是否要换 auth"**：不需要。支付方只提供 `customer_id` + `subscription_id` + webhook，"当前用户是谁"你们已解决得很好。接支付时 auth 只需三处小改：

1. 用户表加一个外部 `billing_customer_id` 列；
2. 新增 webhook 端点，**不能走 `current_user`**（webhook 请求没有你的 cookie），改用**签名验证**；
3. webhook 处理必须**幂等**（支付方会重发）。

### 1.4 服务数量的提醒

pilot 阶段，每多一个服务 = 多一份账单、一处配置、一个故障点。学生团队、线上协作、项目维持阶段，建议控制在**四个**以内：

```
Cloudflare（免费）+ 一个后端平台（含 Postgres）+ Neon（已定）+ Resend（+ R2 待启用）
```

---

## 2. 代码取证：七个落地前必须处理的点

均为本次评估中从源码核实，路径与行号可直接定位。

| # | 问题                     | 位置                                                                                                | 影响                                                                                            | 处理                                                                                                                     |
| - | ---------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1 | **常驻 asyncio 定时器**     | `main.py:34-48`（lifespan 内挂 `weekly_knowledge_summary` 与 `community_aggregate` 两个调度）              | Serverless 实例随用随起随回收，**定时器不会按预期触发**                                                           | 后端改用常驻平台；或把 job 外置为独立进程 / 外部调度                                                                                         |
| 2 | **限流为进程内存**            | `auth/rate_limit.py:12,15`（`_rate_buckets` / `_login_fails`）；文件 docstring 自述"多实例部署需换 Redis"       | 多实例下**计数失效**：5 次失败锁定会变成 5×N 次                                                                 | 照搬仓库**已有的持久化范式**：社区聚合限频已落 `rate_limit_counters` 表（`routes/community.py:121` + `models/rate_limit.py:16`），auth 限流照此改造即可 |
| 3 | **26.5MB 本地 FAISS 索引** | `kb_vectors/embeddings.index`（26.5MB）+ `refs.json`；`vector_store.py:60,72` `_load_from_disk()` 读盘 | Serverless 文件系统**只读**（除 `/tmp`），且每次冷启动重新加载                                                    | 常驻平台无此问题；若坚持 Serverless，索引需迁外部向量服务                                                                                     |
| 4 | **`create_all` 建表**    | `main.py:32`                                                                                      | 现状 SQLite 能糊弄；**Neon 是空库，不跑迁移就没有表**                                                           | ✅ 已解决：squash 出显式基线，空库直接 `alembic upgrade head`，见 §2-4                                                                                       |
| 5 | **CORS 配置会立刻失效**       | `main.py:77-78`：`allow_origins=["*"]` + `allow_credentials=True`                                  | ⚠️ **浏览器规范禁止该组合**。现在不报错只是因为 Vite dev server 代理了 `/api` 走同源，CORS 根本没被触发；**一旦前后端分域名部署，第一个请求就挂** | `allow_origins` 改成显式域名白名单                                                                                              |
| 6 | **Cookie 缺 `Secure`**  | `auth/session.py:43` 手搓 cookie 串，`SameSite=Lax`，无 `Secure`                                        | 同域部署 OK；**跨站部署则 cookie 发不出去**（需 `SameSite=None; Secure`）；HTTPS 生产环境也应加 `Secure`               | 按部署形态调整，**倾向同域部署**（`域/app` + `域/api`）以规避整类问题                                                                           |
| 7 | **无上传路由**              | 全仓 grep `UploadFile` 零命中（OCR 为 501 占位）                                                            | R2 目前**无消费者**                                                                                 | R2 先注册，等 §二期多模态拍照搜题落地再启用                                                                                               |

### 2-4 Alembic 决策必须反转

现状：`docs/archive/backend-changes-plan-a.md` 与提交 `0058917` 明确"schema 唯一真相源是 `create_all`，alembic 迁移降级为留痕，**勿运行 `upgrade head`**"。

上 Neon 后这条必须反过来：

- ✅ **Alembic 成为唯一真相源**，`create_all` 仅保留在测试环境；
- ⚠️ 现有 **13 个 revision**（`alembic/versions/`）需先在**空库**上完整验证能跑通；
- 建议：先在 Neon 开一个分支库验证，再把 `create_all` 从 `main.py:32` 摘掉。

#### ⚠️ 2026-09-15 实测：本节原建议的「空库跑 `alembic upgrade head`」**不成立**

在本地空 SQLite 库上实跑，**第二个 revision 就失败**：

```
sqlite3.OperationalError: table kb_subjects already exists
```

根因：基线 `ee1d7e6e893c` 的 `upgrade()` 是 `Base.metadata.create_all(bind=op.get_bind())`，
它读的是**当前** metadata（`models/__init__.py` 导入时已注册全部模型），于是建出 **30 张表**
——包含板块二的 `kb_*`、板块三的 `community_*`、`auth_rate_limits`，而该 revision 的
docstring 自称只建"板块一全部 ORM 表"。**基线严重越界。**

连锁后果：后续 12 个 revision 的 **14 处 `create_table` + 14 处 `add_column` 全部冲突**
（表已存在 / 列已存在），整条链从第二个 revision 起**永久不可用**。

**当前可行的建库路径（已实测，产出的 schema 与开发库逐列完全一致：30 张表、0 处差异）**：

```bash
alembic upgrade ee1d7e6e893c   # 基线 create_all 建全部表
alembic stamp head             # 标记为最新版本
```

**✅ squash 已完成（2026-09-15）**：

- 新基线 `1a6f0c6bb285` 由 autogenerate 产出，是**显式 DDL**（29 张表 / 53 个索引），
  不再引用 `Base.metadata`，语义不随模型变化而漂移；
- 旧 14 个 revision 归档到 `alembic/versions_archive/`（不参与 alembic 扫描，仅留痕）；
- 摘掉了 `models/__init__.py` 里「import 即 create_all」的副作用（autogenerate 能自举的前提）；
  `create_all` 现仅保留在 `main.py`（应用启动）与 `tests/conftest.py`（测试重建）；
  三个依赖该副作用的脚本（`import_knowledge_points.py` / `migrate_subject_codes.py` /
  `seed_kb_physics_english.py`）已补上显式建表。

**验证结果**（本地 SQLite）：

| 检查项 | 结果 |
| --- | --- |
| 空库 `alembic upgrade head` | ✅ 无报错，建出 30 张表（29 业务 + alembic_version） |
| 与开发库逐列对比 | ✅ **0 差异**（列 / 类型 / nullable / 默认值 / 索引） |
| `downgrade base` → 再 `upgrade head` | ✅ 可反复执行 |
| `pytest` | ✅ 284 passed / 1 skipped |
| 脚本在空库上运行 | ✅ 29 张表正常建出 |
| 应用在空库上启动 | ✅ 建表 + 接口响应正确 |

> 验证局限：本次在 SQLite 上做。Postgres 方言差异（如 `BOOLEAN DEFAULT (1)` 这类
> SQLite 习惯写法）仍需在 Neon 分支库上复验——但那要等 P0 平台选型定稿。

---

## 3. 目标部署形态

```
                    Cloudflare（DNS · CDN · SSL）
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
    Vercel（前端静态产物）          常驻容器平台（FastAPI）
    域/  官网（静态化）              域/api
    域/app  应用                       ├─ Neon（Postgres）
                                      ├─ 常驻 job（复用现有 lifespan 调度）
                                      ├─ 本地向量索引（常驻实例内，无冷启动）
                                      └─ Resend（事务性邮件）
```

- **倾向同域**：前端与后端走同一域名不同路径，规避 CORS 凭据与 Cookie `SameSite` 整类问题。
- 若必须分域：CORS 白名单 + `SameSite=None; Secure`，两处都要改。

---

## 4. 落地前必做清单（按优先级）

| 优先级    | 事项                                   | 说明                                                                            |
| ------ | ------------------------------------ | ----------------------------------------------------------------------------- |
| **P0** | 修复 `current_user` 越权                 | ✅ **已完成 2026-09-15**（见附 A）                                                          |
| **P0** | 后端平台选型定稿                             | 卡着后面所有工作量估算                                                                   |
| **P1** | Alembic 空库验证 + 反转建表决策                | ✅ **已完成 2026-09-15**：原计划的 `upgrade head` 跑不通（基线越界建全表）→ 已 squash 为显式基线，空库 upgrade/downgrade 可反复，详见 §2-4 |
| **P1** | CORS 白名单改造                           | ✅ **已完成 2026-09-15**：默认不挂中间件（同域），分域走 `CORS_ALLOW_ORIGINS` 白名单             |
| **P1** | Cookie `Secure` / `SameSite` 按部署形态调整 | ✅ **已完成 2026-09-15**：`COOKIE_SAMESITE` / `COOKIE_SECURE` 可配，None 自动补 Secure  |
| **P2** | auth 限流持久化                           | ✅ **已完成 2026-09-15**（见附 B）                                                    |
| **P2** | 密钥迁入平台 Secrets                       | 现状 `.env` 存明文（`LLM_API_KEY` / `EMBED_API_KEY` / `SMTP_PASS`），未被 git 跟踪但误提交即泄露 |
| **P3** | R2 接入                                | 等有上传路由再做                                                                      |

---

## 5. 待定项

1. **支付服务商选型**（pilot 不收费，不阻塞）：
   - **Stripe**：费率约 2.9% + 0.3，你是 Seller of Record，需合规主体，全球 VAT **自理**；
   - **Paddle / Lemon Squeezy（MoR）**：费率约 5% + 0.5，**他们是卖家**，代管全球税务与发票。
   - 对无公司主体的学生团队，MoR 多付的约 2% 买的是"不用注册公司、不用研究各州各 VAT"。取决于团队实际主体情况。
   - ⚠️ 与产品文档 §7「未成年付费」为同一上线前补项，建议一并决策。
2. **是否启用 WebSocket / SSE**：当前无长连接需求（建议/复盘已是 202 异步 + 轮询），暂不需要。
3. **移动端拍题上传**：§二期多模态，落地时才需要 R2 与上传路由。

---

## 附 A：派发任务单 · `current_user` 越权修复（P0）

> **✅ 已完成（2026-09-15）**，本文档保留作历史记录，**不要重复派发**。
> 实现：`backend/routes/deps.py:current_user` 现在只认 sid cookie，无有效会话一律
> `401 UNAUTHENTICATED`；三层回落链（X-User-ID / Bearer u_ / 匿名兜底 u_10237）由
> 新增配置 `ALLOW_INSECURE_USER_HEADER`（默认 false）控制，测试环境由 conftest 置 true。
> 回归用例见 `backend/tests/test_auth_strict_mode.py`（8 条）。
> 附带修复：测试套件原先直连开发库 `data.db` 与真实 `kb_vectors/` 索引目录，
> 跑一次 pytest 即清空开发数据，已改为隔离到 `backend/.pytest_data/`。

> **以下为原始任务单（已完成，仅存档）。**

> **本任务单自包含，可直接复制给其他 agent / 同学执行。**

### 背景

`backend/routes/deps.py` 的 `current_user` 是一个 FastAPI 依赖，被所有业务路由用于取当前登录用户。它有一条**四层身份回落链**，其中两层允许**请求方自己指定身份**。

### 问题描述

文件：`backend/routes/deps.py`，函数 `current_user`（第 67–99 行）。

```python
def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),   # ← 第 2 层
    sid: str | None = Cookie(default=None),
) -> User:
    ...
    # 2. X-User-ID 头（测试/联调显式指定）
    if user_id is None and x_user_id:
        user_id = x_user_id                                            # ← 任意指定身份

    # 3. Bearer token 里以 u_ 开头的显式 userId（兼容旧测试）
    if user_id is None and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("u_"):
            user_id = token                                            # ← 任意指定身份

    # 4. 无登录态 → 回落到 mock 用户
    if user_id is None:
        user_id = "u_10237"                                            # ← 共享账号
```

**两个问题：**

1. **垂直越权（严重）**：任何人发一个 `X-User-ID: u_任意ID`（或 `Authorization: Bearer u_任意ID`）请求头，即可**冒充任意用户**，读写其全部业务数据。注释标注为"测试/联调用"，但代码中**没有任何环境判断**，生产环境同样生效。
2. **匿名兜底**：无会话时统一回落到共享账号 `u_10237`，所有未登录访问共享同一身份。

**复现**（本地起服务后）：

```bash
curl -H "X-User-ID: u_10238" http://localhost:8000/api/v1/me
# 预期应 401，实际返回 u_10238 的用户资料
```

### 修复要求

1. **引入环境开关**：新增配置项（如 `ALLOW_INSECURE_USER_HEADER`），**默认 `false`**；仅测试环境置为 `true`。
2. **生产行为**：
   - 禁用第 2 层（`X-User-ID`）与第 3 层（`Bearer u_`）回落；
   - 无 `sid` 或 `sid` 无效 → 直接 **401**，不再兜底 `u_10237`；
   - 第 1 层（`sid` cookie → `auth_sessions` 表）保持不变。
3. **响应码**：沿用现有统一错误结构 `{ error: { code, message } }`，建议 `code` 用 `UNAUTHORIZED`。

### 验收标准

- [ ] 无 cookie 访问业务接口 → **401**
- [ ] 带 `X-User-ID` 头但无 cookie（生产配置下）→ **401**
- [ ] 带 `Bearer u_xxx` 但无 cookie（生产配置下）→ **401**
- [ ] 带有效 `sid` cookie → 200，返回原用户
- [ ] 测试环境开启开关后，原有用例行为不变
- [ ] `cd backend && pytest` 全绿

### ⚠️ 影响面（务必先处理）

现有测试中 **8 个文件**使用了 `X-User-ID` 头：

```
tests/test_e2e_contract.py(10)  tests/test_me_and_guardian.py(9)
tests/test_weakness_hints.py(3) tests/test_smoke.py(2)
tests/test_community_aggregate_api.py(1)  tests/test_community_consent.py(1)
tests/test_error_book.py(1)     tests/test_rate_limit.py(1)
```

**必须先让这些用例走测试开关**，否则会大面积失败。另有 16 个测试文件直接调用 `client.get/post`，其中可能有依赖匿名兜底的用例——改造时逐一确认。

### 不要做什么

- ❌ 不要改鉴权方式（**不要换成 JWT**），保持 HttpOnly cookie session；
- ❌ 不要改 `current_user` 的返回结构（`schemas/user.py` 的 `User`）；
- ❌ 不要顺手重构 `deps.py` 其他部分，本次只做最小改动；
- ❌ 不要动 `auth/session.py` 的 cookie 生成逻辑（那是另一个任务，见 §2-6）。

### 备注

游客态（产品文档 D1 / D43）将来需要匿名访问非 AI 功能，但**当前 pilot 阶段先统一 401**。等游客态正式实施时再单独设计匿名会话方案——不要在本任务里预留。

---

## 附 B：派发任务单 · auth 限流持久化（P2，接在附 A 之后）

> **✅ 已完成（2026-09-15）**，本文档保留作历史记录，**不要重复派发**。
> 实现：新增 `auth_rate_limits` 表（`scope` 区分 window 计数与 lock 锁定），
> `auth/rate_limit.py` 四个函数签名不变、`routes/auth.py` 零改动；
> 未引入 Redis。回归用例见 `backend/tests/test_auth_rate_limit.py`（10 条）。
> 实测：连续 5 次错误密码后第 6 次 429，**重启进程后仍 429**；发码 60s 内第二次 429，重启后仍 429。

> **以下为原始任务单（已完成，仅存档）。**

### 背景

`backend/auth/rate_limit.py` 的限流与登录失败锁定是**纯进程内存**实现（`_rate_buckets` / `_login_fails` 两个 dict），文件 docstring 自述"多实例部署需换 Redis"。多实例下计数失效：5 次失败锁定会变成 5×N 次。

### 修复要求

**照搬仓库已有的持久化范式，不要引入 Redis**（pilot 阶段不值得多一个组件）：

- 现有范式：`models/rate_limit.py:16` 的 `RateLimitCounter` 表（迁移 `e6f5a4b3c8d9_add_rate_limit_counters.py`），已被 `routes/community.py:121` 用于社区聚合限频；
- 把 `auth/rate_limit.py` 的 `allow` / `is_locked` / `record_fail` / `clear_fails` 改为读写同一张表（或新增并列的表），**保持函数签名不变**，调用方零改动。

### 验收标准

- [ ] 函数签名不变，`routes/auth.py` 调用处无需修改
- [ ] 重启进程后，验证码频控与失败锁定状态**仍然保留**
- [ ] `cd backend && pytest` 全绿（注意 `tests/test_rate_limit.py`）

### 不要做什么

- ❌ 不要引入 Redis（pilot 阶段增加组件不划算）；
- ❌ 不要改 `MAX_FAILS = 5` / `LOCK_MS = 15 分钟` 这些阈值；
- ❌ 不要改限流的对外行为（429 的 code / message 保持 `RATE_LIMITED`）。

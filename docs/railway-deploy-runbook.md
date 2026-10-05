# Railway 部署 runbook（EpochX 后端）

> 平台：Railway（Skyer 2026-10-04 拍板）
> 配置：`.railway/railway.py`（Infrastructure as Code，Python beta 作者接口）
> 构建脚本：`scripts/railway_build.py`
> 关联：pilot 一期前置 §5 第 8 项「向量检索 pilot 期可用」的 ② 待部署落地
> 作者：dev-4 · 2026-10-05

---

## 0. 一分钟摘要

| 项 | 值 |
|---|---|
| 服务名 / 副本 | `backend` / **1（不可调高，原因见 §4）** |
| build | `python scripts/railway_build.py` |
| start | `cd backend && python ../scripts/check_vector_index.py && exec uvicorn main:app --host 0.0.0.0 --port $PORT` |
| pre-deploy | `cd backend && python -m alembic upgrade head` |
| healthcheck | 路径 `/health`，超时 300s |
| 索引来源 | build 时从 `KB_VECTOR_URL` 下载 → `KB_VECTOR_DIR=/app/kb_vectors` |
| 变量总数 | 19（其中 **11 个用 `preserve()`**，本文件不含任何真实凭据） |
| 部署者| Railway 后台相关步骤由 **Skyer** 执行（我们没有账号权限） |

---

## 1. 为什么用 IaC 而不是 `railway.json`

官方文档已把 Config as Code 标为**废弃**：

> 「Config as Code is **deprecated**… Existing files keep working for legacy services until
> **2026-12-01**」；「**New services cannot opt into Config as Code**.」

即 `railway.json` 对**新服务已经不可用**，写了也白写。所以直接上 `.railway/railway.py`。

### 两个容易搞混的差异（踩过）

1. **`.railway/` 不参与部署。** IaC 由 CLI 的 `railway config plan` / `apply` 评估，
   把 build / start / healthcheck **推到服务设置上**，之后的部署才用这些设置。
   → **改完 `.railway/railway.py` 不 `apply` 等于没改。**
2. **作者API 的 key 大小写是混的**（已用 `railway-sdk` 源码核对）：
   `build` / `start` / `healthcheck` 小写，但 **`preDeploy` / `healthcheckTimeout` 是驼峰**。
   `service(name, **config)` 接受任意 kwargs → **写错 key 不报错，只是那一项被静默丢掉。**

---

## 2. 前置条件

| # | 事项 | 谁做 |
|---|---|---|
| 1 | Railway 账号与项目已建，项目名与 `project("epochx", ...)` 一致 | Skyer |
| 2 | 本机装 CLI + SDK：`npm i -g @railway/cli` / `pip install railway-sdk` | 任意 agent |
| 3 | `railway login && railway link` 关联到目标项目与环境 | 任意 agent |
| 4 | **把索引传到对象存储**，得到一个目录 URL（其下有 `embeddings.index` 与 `refs.json`） | **Skyer**（见 §3） |
| 5 | 在 Railway 配齐 §5 的 19 个变量（11 个 `preserve()` 的必须**先在后台填好值**，否则 `apply` 后服务起不来） | **Skyer** |

---

## 3. 🔴 索引送达：唯一无法在仓库内解决的一环

### 为什么必须从外部送

两条路都堵死，**都不是配置能绕开的**：

- **进不了 git**：`.gitignore` 第 28 行就是 `backend/kb_vectors/`，`git ls-files backend/kb_vectors/` 为空
- **不能在 Railway 重建**：源 JSON 在 `D:\Projects\knowledge base\docs\knowledge-points\`，
  **在仓库之外**；而重建要 3391 次embedding API 调用（上次全量导入实测 **1241 秒**≈ 21 分钟），
  有build 超时风险且花钱

### 采用的机制（用户 2026-10-05拍板：方案 A）

build 时从 `KB_VECTOR_URL` 下载。`scripts/railway_build.py` 的行为：

1. `KB_VECTOR_URL` **未设置 → 构建直接失败**（exit 1），并打印可操作提示
2. 下载 `embeddings.index` 与 `refs.json` 到 `KB_VECTOR_DIR`
3. 挡住明显失败（小于 1MB / 10KB → 判定下到了错误页或空文件）
4. **跑 `scripts/check_vector_index.py` 做权威校验**（它会真正读 FAISS，
   所以截断/损坏/条目数不对都会暴露）；不通过则**中止构建**

> **设计意图**：宁可**部署失败**，也不要「部署成功但检索静悄悄降级成 name_fuzzy」。
> 后者功能可用、接口形态不变，只是匹配质量下降——**从外部完全看不出来**，
> 只有用户说「搜不准」才会被发现。

### Skyer 需要做的

把两个文件放到一个**可公开读取**的目录（例如对象存储桶或带读 token 的 URL），
把 URL 配成 Railway 变量 `KB_VECTOR_URL`。若用私有桶 + 签名 URL，
**注意签名会过期**——过期的 URL 会让后续每次构建都失败（这是好事，比静默降级强）。

### 方案选择表（lead-1 2026-10-05 要求：说明每个选项在 pilot 期需要回答什么）

> **状态：方案 A 已由用户（代表 Skyer）于 2026-10-05 拍板**，下文 A 是已决方案，
> B/C 列出是为了让接手人知道还有哪些路、以及为什么没选。
> lead-1 在隐退前的最后一条（15:41）倾向「A 之外的 build COPY + volume 兜底」，
> **这个分歧尚未由 Skyer 复核** —— 见文末「待复核的分歧」。

| | **A. build 时从 URL 下载** ✅已定 | B. build 时 COPY（索引进仓库） | C. Railway volume + 状态感知上传 |
|---|---|---|---|
| **怎么做** | `KB_VECTOR_URL` 指向对象存储；`railway_build.py` 下载到 `KB_VECTOR_DIR`，校验不过即中止构建 | 从 `.gitignore` 移除 `backend/kb_vectors/`，Dockerfile/构建里 `COPY kb_vectors/ /app/kb_vectors/` | 挂持久卷，部署后用 `railway run` / `railway ssh` 一次性上传；`KB_VECTOR_DIR` 指向挂载点 |
| **pilot 期要回答什么** | ① 用哪家对象存储<br>② **访问控制怎么配**（公开读 or 签名 URL）<br>③ 若用签名 URL，**过期策略**（每次构建都要重新签？还是有稳定凭据） | ① 26.5MB 二进制进 git 历史后**如何回滚**（历史里删不掉）<br>② 每次 clone 都要拉 26.5MB，团队协作成本<br>③ 索引重建时如何避免一次巨大 diff | ① volume 是否**跨部署保留**（必须实测确认）<br>② 新环境/新区域要不要重新上传<br>③ 首次部署与后续部署的路径不同，是否会漏 |
| **主要风险** | URL 未配/过期 → **构建失败**（可见，安全） | 仓库永久变大；索引泄漏到 git 历史 | **volume 是唯一一份、易丢**；漏传则静默降级 |
| **是否已在仓库实现** | ✅ 已实现并**本地实测**（真实索引 SHA256 逐字节一致） | ❌ 未实现 | ❌ 未实现 |
| **与 brief 的契合度** | 符合 brief「build 时 COPY 或 release 时下载皆可」 | 同上 | 同上 |
| **成本** | 每次构建下载 26.5MB（可接受） | 仓库体积永久增长 | 需确认 volume 是否计费 |

**共同的硬性要求（三个方案都适用，已在代码里定死，不是靠注释）**：
`KB_VECTOR_DIR` 必须显式指向绝对路径；`KB_VECTOR_EXPECTED_COUNT=3391`；
启动前跑 `scripts/check_vector_index.py`，不通过就**拒绝启动**。

> **为什么索引缺失必须让部署/启动失败，而不是降级**：
> 降级后功能可用、接口形态不变，只是匹配质量下降——**从外部完全看不出来**，
> 只有用户说「搜不准」才会被发现。而「放个生成脚本在启动时跑」或「跑完自己删掉」
> 这类做法**比缺索引更糟**：它会产生一个「看起来在用、实际内容不可控」的索引。

### 待复核的分歧（交接给lead-2）

- **用户（代表 Skyer）2026-10-05 15:2x 明确选了方案 A**，我据此实现并本地实测通过。
- **lead-1 隐退前（15:41）倾向「B + C 兜底」**，理由是「冷启动时放生成脚本或跑完自己删掉比缺索引更糟」
  ——这个理由我认同并已写进上文，但它似乎**没有注意到方案 A 已被拍板**。
- **需要 Skyer 复核一次**：若坚持 B 或 C，我可以改配置（改动量很小，主要在
  `railway_build.py` 与 `KB_VECTOR_DIR`），但**方案 C 的volume 跨部署保留语义我无法本地验证**。

---

## 4. 单实例约束（`replicas: 1`，请勿调高）

**两处进程内状态依赖单实例，多副本会同时打破两处：**

| 状态 | 位置 | 多副本后果 |
|---|---|---|
| 限流计数 | `backend/auth/rate_limit.py`，其 docstring 自述「多实例部署需要 Redis」 | 限流被绕过（pilot 可接受） |
| FAISS 索引 | `vector_store` 的进程内 `_index` / `_refs` 全局 | **每个副本各自持一份索引副本**，内存 ×N，且新增向量只进其中一个 |

**pilot 阶段限流不准可接受，索引不能没有** —— 所以这条是硬约束。
Redis 留二期（brief 明确不引入）。

另注：Railway 后台的 replica 数量设置**会覆盖** `.railway/railway.py` 里的 `replicas`，
两处都要是 1。

### 决策状态（lead-2 2026-10-05 定稿）

| 项 | 状态 |
|---|---|
| 索引送达方案 | ✅ **A + Cloudflare R2**（私有读 + 预置 URL） |
| `preDeploy` 写生产库 | ✅ **Skyer 明确认可**（原话「可以」），保留不动 |
| 前后端拓扑 | ✅ **分离**：前端 `epochx.net` / 后端 `api.epochx.net` → `BUILD_FRONTEND=0` |
| 项目名 / 域名 / 证书 | ⏳ 取决于 `railway config plan` 结果，改配置即可；plan 不动也能继续 |
| 用户数据 / embedding 边界 | 由 dev-2（数据/合规）与 dev-1（前端/合规）确认；本服务**不新增** `EMBED_*` 密钥调用 |

> **`KB_VECTOR_URL` 需要一个 R2 上的预置 URL。** R2 是私有读，所以这个 URL 要么带签名、
> 要么由 Cloudflare 侧配好可读路径。**若用签名 URL，过期会让后续每次构建都失败**——
> 这是好事（可见），但要提前决定续签方式，别等构建红了才发现。

---

## 5. 环境变量清单（19 个）

### 必填，且必须在 Railway 后台先有值（`preserve()` = 保留后台已有值）

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | **必须指向 Neon**，且 psycopg2 可直连的 DSN（`postgresql://`） |
| `JWT_SECRET` |生产必须与本地不同 |
| `KB_VECTOR_URL` | 索引下载源（见 §3） |

### 向量索引（pilot 关键路径）

| 变量 | 值 | 为什么 |
|---|---|---|
| `KB_VECTOR_DIR` | `/app/kb_vectors` | **必须显式设**。生产 `DATABASE_URL` 是 Neon（非 SQLite），不设时 `_index_root()` 回落到进程 cwd，容器重启后路径可能变 → 读不到索引 → 静默降级 |
| `KB_VECTOR_EXPECTED_COUNT` | `3391` | 启动自检基准；不符则打error 日志并暴露在接口上 |
| `KB_EMBED_MODE` | `off` | **绝不能设 `api`**：那样 `add()` 会把向量追加进线上索引、污染检索 |

### 前端

| 变量 | 值 | 说明 |
|---|---|---|
| `BUILD_FRONTEND` | **`0`** | **已定前后端分离**：前端 `epochx.net`（Vercel 等）、后端 `api.epochx.net`（Railway）。<br>此时 `main.py` 对 `/` 与 SPA 路由返回 `FRONTEND_NOT_DEPLOYED` —— **这是预期行为**，API 服务不负责托管 UI。<br>若将来改回同域单服务，把它设成 `1` 并清空 `CORS_ALLOW_ORIGINS` 即可。 |

### 安全 / CORS（前后端分域名部署的连带影响，**这一段最容易踩**）

| 变量 | 值 |
|---|---|
| `CORS_ALLOW_ORIGINS` | `https://epochx.net` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` |
| `ALLOW_INSECURE_USER_HEADER` | **`false`**（true 会允许 `X-User-ID` 头任意冒充用户，只留给本地调试） |

**① `CORS_ALLOW_ORIGINS` 绝不能用 `*`。**
`main.py:85-91` 用的是 `allow_credentials=True`，而**浏览器规范禁止
`allow_origins=["*"] + allow_credentials=True`** —— 带凭据的跨域请求会被直接拒绝。

> 这个坑**已经被踩过一次并修好了**，`main.py:80-82` 留着记录：
> 「原来写的是 `allow_origins=["*"] + allow_credentials=True`……之所以一直没暴露，
> 是因为 Vite dev server 把 `/api` 代理成了同源请求，CORS 从未真正触发；
> **一旦前后端分域名部署，第一个请求就会挂**。」
>
> 本项目正是「前后端分域名部署」，所以这条直接适用。

**② `SameSite` 保持 `lax`，不要改成 `none`。**
`epochx.net` 与 `api.epochx.net` 是**同站不同源** —— `SameSite` 比的是 eTLD+1（`epochx.net`），
**不是 origin**。所以 `Lax` 的 cookie 在跨源 `fetch` 里**照样会带上**。
改成 `none` 会无谓放宽 SameSite 覆盖面，换不来任何东西。

**跨域真正依赖的是**：① 上面那行 CORS 白名单 + `allow_credentials=True`；
② `COOKIE_SECURE=true`（`SameSite=None` 本来也强制要求 Secure，但我们不用 none）。

### 外部服务

`LLM_API_KEY`、`SMTP_HOST`、`SMTP_USER`、`SMTP_PASS` 用 `preserve()`；`SMTP_PROVIDER=real`（字面量）。

#### `EMBED_*`：当前留空（**默认不出域**，但不是「永久不启用」）

`EMBED_API_KEY` / `EMBED_BASE_URL` / `EMBED_MODEL` **当前留空**。

**为什么当前留空**：默认不出域。这既有 Skyer 的决定，也因为历史上**出过配置泄漏导致用户内容出域的事故**
（所以默认值必须保守）。`KB_EMBED_MODE=off` 时 `embedding_service._embed_api` 直接 `return None`
（`embedding_service.py:98-100`），检索走**已有的本地 FAISS 索引**，不碰任何外部 embedding 接口。

**⚠️ 但不要把它读成「永久不启用」—— 这是两道独立的闸**：

| 闸 | 位置 | 语义 |
|---|---|---|
| `KB_EMBED_MODE` | **部署配置**（本文件 / Railway 变量） | 知识库内容是否走外部 embedding 向量化。**默认值** |
| `userContentEmbeddingApiEnabled` | **用户级开关**（契约字段，`b7e3b5d`） | 用户**自行选择**「错题原文/作答/学习记录能否走第三方 API」，**默认关闭** |

Skyer 2026-10-05 把闸门从「禁止配置」挪到了「用户同意」—— **默认关这条底线不变**，
但**用户自己打开开关时，系统就需要 `EMBED_*` 这三个值**。

> **口径更正记录**（两次，值得留着）：
> ① runbook 早前写过「`EMBED_*` 建议配好」——那只是 dev-4 的建议、不是拍板。
> ② 改成「占位 / 线上不启用」后**又纠过头了** —— 那等于把「默认关闭」说成「永远不启用」，
> **替用户做了一个从没经过 Skyer 同意的决定**，比① 更糟。
>
> 记这一笔是因为：**「默认关闭」和「永久不启用」是两个不同的产品决定**，
> 前者是默认值、后者是焊死开关。把建议写成「已建议配置」、或把默认值写成「永久」，
> 都会在交接时被当成既成事实 —— 而这类错误从外表完全看不出来。

**若将来要启用**（用户开关被打开，或需要重建知识库向量）：配置 `EMBED_*` 三项 +
把 `KB_EMBED_MODE` 设为 `api`，并**重新验证 `scripts/check_vector_index.py`**；
注意在索引已存在的容器里切到 `api` 会让 `add()` 向线上索引追加向量、**污染检索**，
正确做法是重建索引而不是复用。

---

## 6. 部署步骤

```bash
pip install railway-sdk
railway login
railway link                # 关联项目 + 环境

railway config plan         # 只读预览，安全
railway config apply        # 确认后才写
```

`plan` 输出里变量值默认脱敏为 `«hidden»`；要看真实值加 `--show-values`。

**CI 门禁**（可选，防漂移）：

```bash
railway config plan --detailed-exit-code   # 无变更 exit 0，有变更 exit 2
```

---

## 7. 部署后验证（**别只看「部署成功」**）

按顺序做完，任何一步不过就不要对外发 pilot：

1. **Railway 日志里搜 `[railway-build] 索引校验通过`** —— 没有这行就是索引没到位
2. `GET /health` → `status: "ok"`（应用 + 数据库）
3. **`GET /health/vector-index`** → 必须是：
   ```json
   { "status": "ok", "searchable": true, "searchMode": "vector",
     "count": 3391, "expectedCount": 3391, "dim": 2048, "refs": 3391,
     "problems": [] }
   ```
   **`searchMode` 若是 `name_fuzzy`，就是静默降级** —— 停，回去查 `KB_VECTOR_URL`
4. 实际检索一次：`GET /points/match?...`，确认走的是向量路径
   （可对照 `searchMode` 与返回的相似度是否非0）
5. `SELECT version_num FROM alembic_version;` 应为 `b7d2e4f1a609`

---

## 8. ⚠️ 哪些「本地跑起来没事、但上 Railway 会出问题」

这一节是本文档存在的核心理由。以下每条都是**本轮实测或查证**得到的，不是预防性提醒。

### 会直接让构建/启动失败的

| # | 问题 | 实测证据 | 处置 |
|---|---|---|---|
| 1 | **`pip install ./backend` 装不上** | `pip install --dry-run --no-deps ./backend` → exit 1，`Multiple top-level packages discovered in a flat-layout`（`backend/pyproject.toml` 无 `[build-system]`，且 `models/` `routes/` `tests/` `alembic/` 是多个顶层目录） | `scripts/railway_build.py` 用 `tomllib` 读 `project.dependencies` 再喂pip，**不新增会漂移的 requirements.txt** |
| 2 | **Railpack 在仓库根探测不到依赖** | 依赖清单在 `backend/pyproject.toml`，而 `root_directory` 是仓库根 | 依赖安装显式写进 build 脚本，不依赖平台探测 |
| 3 | **`KB_VECTOR_URL` 未设则索引送不到** | 索引被 `.gitignore` 排除、源 JSON 在仓库外 | 缺 URL **故意让构建失败**（已本地实测 exit 1） |
| 4 | **`KB_EMBED_MODE` 若误设 `api`** | `add()` 会把向量追加进线上索引 | 配置里钉死 `off`，并在 `.env.example` 与本文件都写了原因 |

### 会「看起来成功但行为不对」的（最危险的一类）

| # | 问题 | 为什么危险 | 处置 |
|---|---|---|---|
| 5 | **`KB_VECTOR_DIR` 不设时静默降级** | 生产是非 SQLite → `_index_root()` 回落到进程 cwd；容器重启后 cwd 可能变 → 读不到索引 → `name_fuzzy`。**日志和响应里都看不出异常** | 配置里显式设 `/app/kb_vectors` + start 前置校验 + 只读接口暴露 |
| 6 | **Railway 没有 `healthcheckCommand`** | 官方 schema 的 `deploy` 只有 `healthcheckPath`（HTTP 路径）与 `healthcheckTimeout`。brief 设想的「`check_vector_index.py` exit 1 → Railway 判不健康」**这套映射不存在** | 索引闸门移到 **start**（启动即失败）；healthcheck 只用 `/health` |
| 7 | **`/health/vector-index` 不能当healthcheck 闸门** | 它在 `degraded` 时仍返回 **HTTP 200**（degraded 是响应体字段，不是状态码） | 同上。**且刻意不改成返回 503** —— Railway 会因此反复重启，而重启修不好缺失的索引，只会造成重启循环 |
| 8 | **`.railway/` 不参与部署** | 改完文件不 `apply` 就完全没生效 | 部署步骤强制走 plan → apply |
| 9 | **作者 key 大小写混用，写错静默丢弃** | `service(name, **config)` 接受任意 kwargs，`preDeploy` 写成 `pre_deploy` 或 `healthcheckTimeout` 写成 `healthcheck_timeout` **都不报错** | 已用真实 SDK 编译验证 17 项断言全过（见 §10） |

### 语义/路径类

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| 10 | **前端产物路径不是 `backend/frontend/dist`** | `main.py:205-206` 是 `Path(__file__).resolve().parent.parent / "frontend" / "dist"` → **仓库根** `frontend/dist`；brief 的「拷进 backend」是错的 | 构建到 `frontend/dist`（默认路径即命中）；另支持 `FRONTEND_DIR` 覆盖 |
| 11 | **不用 `exec` 收不到 SIGTERM** | `exec uvicorn` 让 uvicorn 成为 1 号进程 | start 命令里带 `exec` |
| 12 | **`PORT` 由 Railway 注入** | 不能写死端口 | start 用 `--port $PORT` |

### 本机验证覆盖不到的（**必须由 Skyer 在 Railway 上确认**）

| # | 项 | 为什么本地验不了 |
|---|---|---|
| 13 | **Linux 运行时** | 开发机是 Windows。`faiss-cpu==1.9.0` 有 manylinux wheel（PyPI 可用），但**本机所有验证都不能替代在 Linux 容器里真跑一次** |
| 14 | **Railway 变量注入时机** | build 阶段能否读到 `KB_VECTOR_URL`，只能实测 |
| 15 | **冷启动时长** | 要加载 26.5MB FAISS；`healthcheckTimeout=300` 给的余量是否够，要实测 |
| 16 | **`railway config plan` 的实际 diff** | 需已link 的账号；项目名不一致会plan 出重命名 |
| 17 | **Neon 免费版限制在 Railway 上同样存在** | 只允许 1 个手动快照、无自动备份计划、PITR 仅 6h。换机器不会改变这一点 |
| 18 | **Railpack 镜像只有 `python3`、没有 `python`** | ⚠️ **实测踩中**：首次真实构建 `sh: 1: python: not found` → `exit code: 127` → `Build Failed`。<br>原因：构建镜像 `railpack-builder:mise-2026.9.15` 只提供 `python3`；而**本机 Windows 恰好有 `python.exe`，所以本地永远测不出这个问题**。<br>处置：`buildCommand` 与 `startCommand` **全部改用 `python3`**；`startCommand` 进一步用 `python3 -m uvicorn` 而非裸 `uvicorn`，不依赖 console script 是否在 PATH |
| 19 | **本机 CLI 也需要 `python3`** | 与第 18 条同源、方向相反：Railway CLI 评估 **Python 版 IaC** 时会调 `python3`，而 Windows 上 `python3` 默认是**微软商店占位符**（`WindowsApps\python3.exe`），报「Python was not found」。<br>处置：建隔离 venv（`%LOCALAPPDATA%\railway-iac`）装 `railway-sdk`，并在其 `Scripts\` 内**复制出 `python3.exe`**（必须同目录，`pyvenv.cfg` 才能解析；`.cmd` shim 无效，原生 exe 的 `CreateProcess` 不执行 `.cmd`），再把该目录 prepend 到 PATH。**不动系统 Python** |
| 20 | **`npm install -g @railway/cli` 会卡 15 分钟后失败** | 其 postinstall 要从 GitHub releases 下 `railway.exe`，脚本自己打印 `aborted`。**不是网络问题**——该 URL 实测 HTTP 200、7,989,377 字节可达。<br>处置：手工下载 `railway-<ver>-x86_64-pc-windows-gnu.tar.gz`，把 `railway.exe` 放到 `%APPDATA%\npm\node_modules\@railway\cli\bin\` |
| 21 | **创建带 GitHub source 的服务会立即触发一次构建** | `railway config apply` 新建 service 后，Railway 自动构建 `reason: "deploy"`。**实测无法用 IaC 单独「建服务但不构建」**——`apply` 要求先有 linked project，项目又只能 `railway init` 建，建完就带 source。<br>所以「只 plan 不部署」的边界，在「从零建项目」这一步**做不到**，需要事先知会 |

---

## 9. 待确认事项

| # | 事项 | 状态 |
|---|---|---|
| 1 | **`preDeploy` 跑 `alembic upgrade head`** | ✅ **已获 Skyer 认可（2026-10-05，原话「可以」）**，按现实现保留。会写生产库，失败中止部署是有意的 |
| 2 | 索引托管用哪家对象存储 | ✅ **已定 Cloudflare R2**（私有读 + 预置 URL）。**待办**：确认 R2 URL 的签名/续签方式，避免过期后每次构建都失败 |
| 3 | 项目名 / 域名 / 证书 | ⏳ 跑 `railway config plan` 确认；改名或改配置即可，plan 不通过也能继续 |
| 4 | 前后端拓扑 | ✅ **已定分离**：`epochx.net` + `api.epochx.net`（`BUILD_FRONTEND=0`）。**连带必须做**：CORS 白名单填 `https://epochx.net`（不能用 `*`，见 §5①） |
| 5 | R2 桶的 CORS / 访问路径 | ⏳ 由 Skyer 配 R2 侧访问控制 |
| 6 | 本机 pg_dump 备份是否也上 Railway 定期跑 | Neon 免费版无自动快照，这个缺口在换机器后**依然存在** |

---

## 10. 本轮验证记录（**哪一次、谁跑的、跑的是哪一版**）

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| IaC 配置编译 | 用真实 `railway-sdk` 执行 `.railway/railway.py` 的 `main()`，读 `to_graph()` | **17/17 断言全过**，19 变量、11 个 `preserve()`、无凭据字面量 |
| 依赖解析 | 实跑 `scripts/railway_build.py` 的 `step_install_python_deps` | 从 `pyproject.toml` 解析 12 个 pin 并安装成功 |
| 缺 URL 硬失败 | 不设 `KB_VECTOR_URL` 跑构建 | **exit 1** + 可操作提示 |
| 索引下载真跑 | 本地 `http.server` 供**真实** `backend/kb_vectors/`，`KB_VECTOR_URL` 指向它 | 落地 27,779,117 / 354,166 字节，**SHA256 与源逐字节一致**，`check_vector_index.py` exit 0、`searchMode=vector` |
| Railway 后台全流程 | **未验证**（无账号权限） | 见 §8 第13–16 项 |

> ⚠️ 上表刻意区分「本地已验」与「线上未验」。本轮唯一无法在本地闭环的是
> **Railway 侧的一切**，已在 §8 第 4 节逐条列出。

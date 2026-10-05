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
| `BUILD_FRONTEND` | `1` | `1` = 本服务构建并托管 SPA（**同域，免 CORS**）；`0` = 前端由 Vercel 等单独部署，此时 `main.py` 对 `/` 与 SPA 路由返回 `FRONTEND_NOT_DEPLOYED`（预期行为，不是故障） |

> ⚠️ brief 里这两条是矛盾的（①说「不构建前端」、②说「构建前端拷进 backend」）。
> 选了**默认构建**（`BUILD_FRONTEND=1`）：§3 部署评估本身倾向**同域**
> （「前端与后端走同一域名不同路径，规避 CORS 凭据与 Cookie SameSite 整类问题」），
> 单服务同域是 pilot 期最少变量、最不容易第一次就撞坑的形态。
> 若 Skyer 坚持前后端分离，改这一个变量即可。

### 安全 / CORS

| 变量 | 值 |
|---|---|
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` |
| `ALLOW_INSECURE_USER_HEADER` | **`false`**（true 会允许 `X-User-ID` 头任意冒充用户，只留给本地调试） |
| `CORS_ALLOW_ORIGINS` | `preserve()` — 同域时留空即可；前后端分离时**必须**改成前端域名 |

### 外部服务（全部 `preserve()`）

`LLM_API_KEY`、`EMBED_API_KEY`、`EMBED_BASE_URL`、`EMBED_MODEL`、
`SMTP_HOST`、`SMTP_USER`、`SMTP_PASS`；`SMTP_PROVIDER=real`（字面量）。

> ⚠️ **`KB_EMBED_MODE=off` 时 `EMBED_*` 不会被调用**，但仍建议配好——
> 万一将来要重建索引或加错题向量化，缺key 会直接失败。

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

---

## 9. 待确认事项

| # | 事项 | 状态 |
|---|---|---|
| 1 | **`preDeploy` 跑 `alembic upgrade head`** |⚠️ **会写生产库**；失败会中止部署（这是有意的：宁可不部署，也不要带旧 schema 上线）。用户已同意放，但**需lead-1 / Skyer 拍板**。若不接受，改为写进 runbook 手动执行 |
| 2 | 索引托管用哪家对象存储 | 待 Skyer（我不编造服务名） |
| 3 | 项目名是否为 `epochx` | 待 Skyer；不一致时改 `.railway/railway.py` 的 `project("epochx", ...)` |
| 4 | 前后端是否分离 | 默认同域单服务（`BUILD_FRONTEND=1`）；分离只改这一个变量 |
| 5 | 本机 pg dump 备份是否也上 Railway 定期跑 | Neon 免费版无自动快照，这个缺口在换机器后**依然存在** |

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

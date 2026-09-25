# OpenMAIC 参考笔记（面向 2.0「桌面端 + agent harness」）

> **性质**：外部项目调研笔记，**活跃参考**，非契约、非行动依据。
> 来源：https://github.com/THU-MAIC/OpenMAIC （MIT）· 调研日期 2026-09-22 · 对应仓库 `main` @ `2026-09-21`
> 动机：`pending-decisions.md` **#53** —— 愿景 pilot → beta → 正式 → **2.0（桌面端 + agent harness）**，
> 且要求「**2.0 的 agent harness 现在就保持 LLM 与业务逻辑解耦**」。本笔记回答：OpenMAIC 对这件事有没有用。

---

## 0. 一句话结论

**OpenMAIC 本身不是我们要的东西**（它是「一键生成多智能体互动课堂」的完整产品，Next.js 栈，定位与我们不重叠）；
**但它把一个 agent harness 从零写到生产级，用的底座是 `Pi Agent Harness`（`@earendil-works/pi-*`）——那才是我们 2.0 真正该研究的东西**。
OpenMAIC 的价值 = ① 一份「如何用 pi 搭出产品级 harness」的**完整参考实现**（含崩溃恢复、事件协议、存储契约、权限边界）；
② 一批**可直接抄格式**的契约文档与设计决策。

**分层结论**：

| 层 | 有没有用 | 怎么用 |
|---|---|---|
| **`Pi Agent Harness`（`@earendil-works/pi-*`）** | ⭐ **最有用** | 2.0 的 harness 底座候选：MIT、TS、10.8 万 star、官方 SQLite session backend、`streamProxy` 天然适配「前端跑循环 + 后端只代理」 |
| **OpenMAIC 的 harness 实现**（`lib/server/agent-runtime/`） | ✅ 有用 | 当**参考实现**读：崩溃恢复语义、事件协议、CAS 并发、能力边界 fail-loud |
| **OpenMAIC 的存储契约文档** | ✅ 有用 | 直接抄**文档格式**（错误码表 + 客户端映射 + 重试/原子性保证），补我们 `openapi.yaml` 的短板 |
| **OpenMAIC 产品本身** | ❌ 不用 | 定位不同（生成课堂 vs 学习状态管理）；栈不同（Next 16 / React 19 / Tailwind 4 / shadcn vs 我们 antd + CSS Modules） |
| **OpenMAIC 的 24 个 K12 skills** | 🔍 待看 | `k12-core-literacy-planning` / `learning-to-learn` / `feynman-learning` / `social-emotional-learning` 是**内容资产**，与 Chat 人格、建议语气可能相关 |

---

## 1. OpenMAIC 事实卡（核实过，别信印象）

| 项 | 事实 |
|---|---|
| 定位 | Open Multi-Agent Interactive Classroom —— 把任何主题/文档变成互动课堂（课件、测验、仿真、PBL），AI 老师 + AI 同学 |
| 许可 | **MIT**（v0.3.0 起由 AGPL-3.0 改 MIT）；子包例外：`mathml2omml` 为 LGPL-3.0-or-later |
| 规模 | 3069 个文件；`main` 分支 610 commits / 96 tags；最新提交 2026-09-21（活跃） |
| 技术栈 | Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS 4 · shadcn/Radix · **LangGraph 1.1**（多 agent 编排）· zod 4 |
| 后端形态 | 无独立后端服务：Next.js App Router 的 `/api/*` + 内嵌持久化（PostgreSQL） |
| harness 底座 | **`@earendil-works/pi-agent-core@0.78.0` + `@earendil-works/pi-ai@0.78.0`**（pin 精确版本） |
| 桌面端 | **没有**。全仓搜 `electron` / `tauri` / `desktop` → 只有一张 `desktop_interactive.png` 示意图 |
| "harness" 一词 | OpenMAIC 仓库里**不出现**；它叫 `agent-runtime`。**"harness" 是上游 pi 的自称** |

---

## 2. 关键发现：harness 在 pi，不在 OpenMAIC

OpenMAIC 的 agent 能力不是自己从零写的，而是搭在 **Pi** 上。

**Pi = 「Pi Agent Harness」**（https://pi.dev · github.com/earendil-works/pi）

| 项 | 事实 |
|---|---|
| 维护者 | **mitsuhiko（Armin Ronacher，Flask/Jinja 作者）** + badlogic（Mario Zechner） |
| 许可 / 语言 | **MIT** / TypeScript |
| 热度 | **108,068 star**、13,669 fork（2026-09-22 实测） |
| 起始 | 2025-08-09 创建，最新提交 2026-09-21（高度活跃） |
| 包家族 | `pi-coding-agent`（CLI）· `pi-agent-core`（agent 运行时）· `pi-ai`（统一多 provider LLM API）· **`pi-durable`**（durable conversation/task/document runtime，**很早期：仅 3 个版本**）· `pi-tui`（终端 UI，差分渲染）· `chord`（应用组合运行时 / RPC / 插件）· `pi-telemetry` |
| 官方二进制 | 有 standalone binaries 构建脚本（README 只给 `linux-x64` 示例，**Windows 是否官方支持待核实**） |
| 权限模型 | **没有内建权限系统**，默认继承进程权限；要隔离需容器化（Gondolin micro-VM / Docker / OpenShell 三种模式） |
| Python 支持 | **无**。全家族 TS-only |

### 为什么这对「桌面端 harness」是关键

`pi-agent-core` 的 API 形状恰好是桌面端需要的：

- **`streamProxy`**：官方提供「浏览器/客户端跑 agent 循环，只把模型调用代理给后端」的模式
  → 桌面端进程内跑 harness、**FastAPI 退化为「模型代理 + 业务事实计算 + 持久化」**，与我们现有后端不冲突
- **SQLite session backend**（`@earendil-works/pi-session-backend-sqlite-node`）：一个 Session 一个 sqlite 文件、
  支持 `createBranch()` 分支、明确「宿主负责保证同一 Session 只有一个可写 owner」
  → **桌面端本地持久化的官方路径**，不用自己发明
- **`beforeToolCall` / `afterToolCall` 钩子**：可在工具执行前拦截并 `block`
  → 正是我们「**权限不给模型**」那条红线（锚定确认卡）的落点
- **steering / followUp 双队列**：运行中插话（steer）与跑完后追加（follow-up）分离
  → 对应我们 Chat 的「挂起 / 追加」设计（#45）
- **`AgentMessage` vs LLM Message 双层**（`convertToLlm` 过滤）：支持**自定义 UI-only 消息类型**
  → 我们的「引用块 / 卡片 / 锚定确认卡」天然属于这一层，不用污染 LLM 上下文
- **事件流协议**：`agent_start / turn_start / message_update / tool_execution_* / turn_end / agent_end`
  → 可直接当我们的流式 UI 事件契约底稿

⚠️ 但要注意：**pi 是 TS，我们是 Python/FastAPI**。这不是能"顺手引入"的依赖，而是一个**架构决策**（见 §5）。

---

## 3. OpenMAIC 里值得逐文件读的 6 处

路径均在 `THU-MAIC/OpenMAIC@main`。

### 3.1 `lib/server/agent-runtime/resume.ts` —— 崩溃恢复语义（**最值得抄的一份**）

`planResume(transcript)` 把"崩溃截断的 transcript"分类成 5 种尾部状态，再决定 `start` / `continue` / `already-complete`：

| 尾部状态 | 处理 |
|---|---|
| 空 | `start`（什么都没跑） |
| 以 `user` 结尾 | `continue`（prompt 记下了，助手回合没完成） |
| 以 `toolResult` 结尾 | `continue`；**但尾部成功的 `ask_user` 视为终态**（否则 agent 会回答自己的问题） |
| 以 `assistant` + 未答 toolCall 结尾 | 报告 dangling id，由共享读边界补"中断结果" |
| 以 `assistant` 无 toolCall 结尾 | `already-complete` |

**核心推论（务必记住）**：中断结果修复让工具执行变成 **at-least-once** →
**这个系统里每个工具都必须幂等**。所以 `putScene` 的幂等键是 `(stageId, sceneId)`，
`generate_scene` 的 scene id 从大纲条目推导而非新铸。

→ 我们写 harness 时最容易漏、最难事后补的就是这一段。**现在就把工具幂等性当契约写下来**。

### 3.2 `lib/agent-runtime/lifecycle.ts` —— 事件协议（跨 wire 共享、live 与 replay 必须一致）

要点（注释里全是决策记录，值得整段读）：

- 事件名放在**服务端与浏览器都能 import、且不引入 db 依赖**的位置 —— 注释原话：
  「importing it must never pull a database dependency into the client bundle」
- 浏览器必须**按名字订阅具名 SSE frame**（`EventSource` 只把 `event: user_question` 投给注册了该类型的监听器，不会进 `onmessage`）
- **live 与 replay 必须一致**：`thinking_end` 被刻意做成 durable frame，因为 token delta 会在 replay 时被 compact 掉 ——
  「the bar's clock stops at the same instant live and on replay」
- **事件演进要有 durable 兼容**：改名后旧事件名（`course_link`）已写进历史日志 → 浏览器 replay 时必须**两个名字都接受**
- **一个事件覆盖四种变更**（`library_changed`）：因为消费者的问题不是"什么变了"，而是"我的树是否过期"

→ 与我们的相关性：我们有「**不做对话历史**但会话内要能 replay」的独特设计（D45 / §3.8），
**live/replay 一致性**这条会直接变成坑。这份文件是现成的解法。

### 3.3 `packages/@openmaic/storage/docs/runtime-http-contract.md` —— 契约文档的写法模板

一份存储层 HTTP 契约包含：端点表 → 服务端赋值语义（`seq` / `runtimeDslVersion`）→
**CAS 守卫**（`expectedLastSeq`，冲突返回 `409 RUNTIME_APPEND_CONFLICT` 且两个变更都不提交）→
载荷域（明确拒绝 `Map`/`Set`/`Date`/`bigint`/`NaN` 等）→ **错误码表 + 客户端如何映射**（只有 `SESSION_NOT_FOUND` 才翻译成 `undefined`）→
**重试与原子性保证**（哪些可安全重试、哪些不可）→ **安全模型**（`learnerKey` 是分区键，**不是身份证明**，服务端必须从认证态派生，否则横向越权）。

→ 我们 `openapi.yaml` 有 51 paths / 162 schemas，但**没有"客户端如何映射错误码"和"哪些操作可重试"这两节**。
建议照这份的目录补两节，成本低、收益高。

### 3.4 `lib/server/agent-runtime/agent-driver-model.ts` —— 能力边界 fail-loud

- `MODEL_ROUTES` 必须**显式**把 driver stage 路由到**带 provider 前缀**的模型，**故意没有 fallback**
- 前缀缺失 / api 方言不支持 / 不该设的 thinking 参数 → **启动即抛错**，不猜厂商
- 注释解释为什么：`parseModelString` 会把裸 model id 静默默认到 openai provider，
  所以必须在到达那个 fallback 之前失败

→ 这就是 D53「**LLM 与业务逻辑解耦**」的具体样子：路由是**配置**，解析是**独立的一层**，错了就**大声失败**。

### 3.5 `lib/choreography/` + ESLint 边界规则 —— 「单一真相源 + 机器强制」

把「播放语义」抽成 `lib/choreography/` 作为**唯一真相源**，让 app runtime 与导出器解释同一份规范，
而不是各自实现、静默漂移。纯度靠 **ESLint 边界规则机器强制**：禁止 `@/` 宿主路径，禁止 react / gsap / framer-motion。

→ 我们已有「契约先行」（`openapi.yaml` 唯一真相源）文化，但**强制手段只有评审**。
可借鉴：把跨模块语义抽成纯函数单源 + 用 lint 禁依赖，比靠人守规矩可靠。

### 3.6 `skills/agent-runtime/*/SKILL.md` —— 24 个内置技能

标准 `SKILL.md` 格式（与 WorkBuddy / Codex 生态通用），24 个内置 + 用户技能（每 owner 50 配额，可增删改）。
其中与**我们面向中学生**直接相关的内容资产：

- `k12-core-literacy-planning`（含 `references/subjects/{mathematics,science,languages,humanities}.md`）
- `learning-to-learn` · `feynman-learning` · `social-emotional-learning` · `spiral-curriculum` · `curriculum-planner`

→ 这些是**教学法内容**，不是代码。是否与我们 Chat 的"建议语气 / 归因回应"有关，需要人读一遍再判断（**未读，待评估**）。

---

## 4. 顺带发现的、与 harness 无关但有用的

- **OpenMAIC 的 `skills/openmaic/` 明确支持 WorkBuddy**（README 原文列出 Codex / DeepSeek / WorkBuddy），
  且提供 Live Demo（open.maic.chat）。→ 如果我们想看它的**实际产出**（互动课堂效果），
  不需要本地跑，装它的 skill 或直接用 hosted 版即可。**这是评估「我们的知识页/讲解要不要做到这个程度」的最省力路径。**
- **编排与 harness 是两层**：OpenMAIC 用 LangGraph 做多 agent 编排，同时用 pi 做单 agent 循环。
  → 我们若要"多角色"（如「规划者 + 讲解者」），**不必让 harness 承担编排**。
- **`render-service`**：独立容器跑 Headless Chromium + FFmpeg 做 MP4 导出，带 CSP 隔离不可信 HTML、
  Puppeteer 请求守卫、chunk 级 semaphore 与资源 profile。
  → 与"桌面端"关系不大，但若以后要做"导出/分享"，这是一个成熟的隔离范式。

---

## 5. 与我们现有架构的冲突与判断

### 5.1 硬冲突：**语言**（这是必须先拍板的）

| | EpochX | pi / OpenMAIC |
|---|---|---|
| 后端 | **Python / FastAPI / SQLAlchemy / Alembic** | TypeScript / Node ≥ 22.19 |
| 前端 | React 18 + antd 5 + CSS Modules | React 19 + Next 16 + Tailwind 4 + shadcn |

**三条路，没有第四条**：

| 方案 | 做法 | 代价 | 判断 |
|---|---|---|---|
| **A. harness 跑在桌面端进程（TS）** | Electron 主进程 / Tauri sidecar 内跑 `pi-agent-core`；FastAPI 退化为「模型代理 + 业务事实计算 + 持久化」 | 需要定桌面端技术栈；引入 TS 的 harness 生态 | ⭐ **推荐**。与 pi 的 `streamProxy` 设计吻合，FastAPI 不用重写 |
| **B. harness 跑在 Python 侧** | 自己实现循环，**只借鉴** pi/OpenMAIC 的语义（resume / lease / CAS / 事件协议） | 自己踩所有崩溃恢复的坑 | 可接受，但要把 §3.1 那份语义**当规格抄全**，否则一定漏 |
| **C. 后端整体迁 TS** | 与 pi 同栈 | 推翻 FastAPI + Alembic + 47 张表 | ❌ 现阶段不现实 |

⚠️ **不管选 A 还是 B，现在要做的是同一件事**：把 Chat 内核的「循环 / 状态 / 工具协议」与「业务事实计算（状态引擎、mastery、画像提取）」**切开**。
这正是 #53 说的「现在就保持解耦」—— 现在切，2.0 才有得选。

### 5.2 不冲突但要注意

- **合规**：pi 无内建权限系统。我们的未成年红线（数据不出境、错题 embedding 本地化、监护人授权）
  **必须在我们这一层实现**，不能指望 harness。若走方案 A，模型调用点在哪、走了哪条链路，要在架构图里画清楚。
- **`pi-durable` 现在别用**：仅 3 个版本、公开 API 只有 `MemoryStorage` + 记录契约。要用就先用 `pi-agent-core` + 官方 SQLite backend。
- **`pi-agent-core@0.78.0` vs 最新 `0.86.1`**：OpenMAIC pin 在 0.78.0（他们的 supply-chain 纪律是 pin 精确版本）。
  我们自己选版本时注意 API 面在动。
- **别照搬 OpenMAIC 的前端栈**：Tailwind 4 + shadcn 与我们 antd + CSS Modules 冲突（与「视觉统一」目标直接矛盾，见项目记忆）。

---

## 6. 建议动作（按性价比排序）

1. **读三份文件就够开工**（约 1 小时，不改任何代码）：
   `resume.ts`（崩溃恢复）→ `lifecycle.ts`（事件协议）→ `runtime-http-contract.md`（契约写法）。
   这三份合起来 = 一份 harness 的**最小正确性规格**。
2. **给 `openapi.yaml` 补两节**（低成本高收益，走 X0 评审）：
   ① 错误码表 + **客户端如何映射**；② 每个写操作的**可重试性**声明。
   照 `runtime-http-contract.md` 的目录抄格式即可。
3. **在 B 板块契约里加一条**：**「所有工具必须幂等」**，并给每个工具写幂等键。
   理由见 §3.1 —— 崩溃恢复会重放工具调用，这不是可选项。
4. **评估 `pi-agent-core` 的实测**（半人日）：起一个最小 Electron/Tauri 壳，跑通
   `Agent` + `streamProxy` + SQLite session backend，验证「桌面端进程内跑循环、FastAPI 只代理」这条链路。
   **结论会直接决定 §5.1 选 A 还是 B**，所以宜早不宜晚。
5. **把 2.0 的 harness 决策写成独立文档**（`docs/adr-agent-harness.md`），别混进 `product-redesign-target.md`。
   照 #51 的先例：**UI 视觉单开文档，架构决策也单开**。

---

## 附：可复现的核查命令

```bash
# OpenMAIC 仓库信息（无需 token）
curl -s https://api.github.com/repos/THU-MAIC/OpenMAIC | python -c "import json,sys;d=json.load(sys.stdin);print(d['stargazers_count'],d['license']['spdx_id'],d['pushed_at'])"

# pi 仓库信息
curl -s https://api.github.com/repos/earendil-works/pi | python -c "import json,sys;d=json.load(sys.stdin);print(d['stargazers_count'],d['license']['spdx_id'],d['description'])"

# 确认 OpenMAIC 没有桌面端（应只剩 1 张 png）
curl -s "https://api.github.com/repos/THU-MAIC/OpenMAIC/git/trees/main?recursive=1" | python -c "
import json,sys
t=[x['path'] for x in json.load(sys.stdin)['tree']]
print([p for p in t if any(k in p.lower() for k in ('electron','tauri','harness','desktop'))])"

# OpenMAIC 的 pi 版本 pin
curl -s https://raw.githubusercontent.com/THU-MAIC/OpenMAIC/main/package.json | python -c "import json,sys;d=json.load(sys.stdin);print({k:v for k,v in d['dependencies'].items() if 'earendil' in k})"
```

---

*本笔记不构成行动依据。落地前请与 `docs/README.md`、`refactor-module-contracts.md`（B 板块）对齐，并走 X0 评审。*

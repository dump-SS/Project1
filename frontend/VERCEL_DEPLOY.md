# 前端部署（Vercel 侧）· EpochX

> 范围：**只写前端侧**。后端部署见 `docs/railway-deploy-runbook.md`（作者 dev-4，本文不改动它）。
> 作者：dev-6 · 2026-10-05
> 状态：配置文件形态**已定稿**（`vercel.ts`）；Vercel 项目创建 / 域名 / 环境变量落地仍**待补**（见 §6）

---

## 0. 一分钟摘要

| 项 | 值 / 状态 |
|---|---|
| 部署形态 | 前后端分离：前端 Vercel + 后端 Railway（Skyer 2026-10-05 定） |
| 前端域名 | `epochx.net`（apex）；后端 `api.epochx.net` |
| 两者关系 | 同域不同子域 → **same-site** |
| SPA history 回退 | **必须配**，否则 `/study-timer` 等深链 404（证据见 §1） |
| 配置文件 | **`frontend/vercel.ts`** ✅ 已定稿（Skyer 确认走 IaC） |
| 实现方式 | `rewrites`，**不用** `routes`（理由见 §3，含官方出处） |
| 新增依赖 | `@vercel/config@0.9.0`，放在 **`devDependencies`**（精确 pin，唯一新增） |
| `VITE_API_BASE_URL` | 分离部署设为 `https://api.epochx.net/api/v1`（绝对地址，见 §4） |
| 未提交 | 全部留在工作区，等 lead-2 review |

---

## 1. 为什么需要 SPA history 回退（含本地实测证据）

前端是 `react-router-dom` v6 的 SPA，路由表在 `src/App.jsx`，共 **22 处 `path=` 声明**，包括：

```
/  /docs/*  /login  /register  /forgot-password  /study-guide  /study-plan
/study-timer  /personal-data  /goals  /settings  /summary-review
/recommendations  /profile-setup  /guardian-auth  /knowledge  /error-book
/chat  /community  /community/upload  /community/compare  *
```

Vercel 托管静态产物时，**默认行为是：拿请求路径去找同名静态文件，找不到就返回 404，不会回退 `index.html`**。

### 实测证据（本机 `npm run build` 真实产物）

跑 `npm run build`（exit 0）后检查 `dist/`：

| 检查 | 结果 |
|---|---|
| `dist/index.html` 存在 | **True** |
| `dist/` 顶层内容 | `assets/` `brand/` `cards/` `fonts/` `slides/` + 3 个媒体文件 + `index.html` |
| 名为 `study-timer` / `goals` / `chat` / `error-book` / `settings` 的文件（递归扫全 dist） | **匹配 0 个** |

即：磁盘上**只有** `index.html` 和 `/assets/*`，`/study-timer` 没有任何对应文件。
→ Vercel 上访问 `/study-timer` 必然 404 → **回退不是优化项，是必需项**。

**后果**：用户刷新页面或直接粘贴深链 → 404。站内点击（客户端路由）不受影响，
所以这个洞**只在「刷新 / 外部分享 / 收藏夹」时暴露，很容易漏测**。

> 三件套：命令 `Get-ChildItem -Recurse -File | Where-Object { $_.Name -match 'study-timer|goals|chat|error-book|settings' }`；
> cwd = `D:\Projects\Project1\frontend`；扫描计数 = **0 个匹配**。

---

## 2. 配置文件：`frontend/vercel.ts`（已定稿）

**为什么是 vercel.ts 而不是 vercel.json**：Skyer 2026-10-05 定的前后端分离形态要求 Vercel 侧走 IaC，
与本仓库 Railway 侧的 `.railway/railway.py` 同一思路（那里也是因为 `railway.json` 已废弃才改用代码化 IaC）。

**官方硬约束（二者只能存在一个）**：

> "Use only one configuration file: `vercel.ts` or `vercel.json`."
> —— https://vercel.com/docs/project-configuration/vercel-ts

→ 所以仓库里**绝不能同时出现** `vercel.ts` 与 `vercel.json`。本文件与 `vercel.json` 互斥。

### 2.1 文件位置：`frontend/vercel.ts`，不是仓库根

因为 Vercel 项目的 Root Directory 设为 `frontend`，配置文件放在 Root Directory 下。

官方 monorepo 文档的措辞是「放在 app 的根目录」，且示例都在子目录：

> "Specify `@vercel/related-projects` … in a `vercel.json` configuration file
> **at the root of the app**."
> ```json filename="apps/frontend/vercel.json"
> { "relatedProjects": ["prj_123"] }
> ```
> —— https://vercel.com/docs/monorepos

同页另有 `**apps/web/vercel.json**` 的 installCommand 示例，同样在子目录。

> ⚠️ 官方示例用的是 `vercel.json`，位置口径对 `vercel.ts` 同理（同一个"只能选一个"的机制），
> 但**「Root Directory = frontend 时能否读到 `frontend/vercel.ts`」本身未实测**（无 Vercel 项目）。见 §7。

---

## 3. SPA 回退：用 `rewrites`，不要用 `routes`

两者都能做 SPA 回退，但官方明确把 `routes` 的关键能力标为废弃。**以下均为 Vercel 官方文档原文**。

### 3.1 官方给的 SPA 示例就是它

> `vercel.json` 参考页 · rewrites 章节：
> "This example rewrites all requests to the root path which is often used for a Single Page Application (SPA)."
> ```json
> { "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
> ```

### 3.2 `rewrites` 默认先查文件系统 —— 所以一条 `/(.*)` 就够

> "The `source` property should **NOT** be a file because **precedence is given to the filesystem
> prior to rewrites being applied**."
>
> "Use `rewrites` instead, **which checks the filesystem by default**."（讲废弃的 `handle` 属性时）

即 `/assets/index-abc123.js` 这类**存在的**文件先由文件系统命中，永远走不到 rewrite；
只有**未命中**的路径才回退 `index.html`。所以不需要为 assets 单独开排除规则。

### 3.3 用 `routes` 实现同一件事要靠已废弃的属性

> "The following route properties are **deprecated**:
> - `handle`: A special route type (e.g., `"handle": "filesystem"`) that controls routing phases.
>   Use `rewrites` instead, which checks the filesystem by default.
> - `override`: A boolean that overrides the matched path in the filesystem. Use `rewrites` instead."

`handle: filesystem` 与 `override` 正是手写 SPA 回退要用的两根杠杆，而它们都已废弃。

### 3.4 Vite 项目的官方口径（**注意：官方没有逐字写「Vite 支持 rewrites」**）

`https://vercel.com/docs/routing/rewrites` 的 "Framework considerations" 原文：

> "**Rewrites to external origins** work universally with all frameworks, making them ideal for
> API proxying, microfrontend architectures, and serving content from external origins…
>
> For **same-application rewrites**, always prefer your framework's native routing capabilities:
> - **Next.js**: Next.js rewrites
> - **Astro**: Astro routing
> - **SvelteKit**: SvelteKit routing
>
> Use `vercel.json` rewrites for same-application routing **only when your framework doesn't provide
> native routing features**. Always consult your framework's documentation for the recommended approach."

**两点要如实说清：**

1. **官方并未说 Astro / SvelteKit「不支持 rewrites」** —— 它说的是「优先用框架原生路由」。
   （此前 brief 里「官方明确列了 Astro / SvelteKit 不支持 rewrites」的说法与原文不符，已更正。）
2. **Vite 不在那个推荐列表里**，而 Vite 本身没有服务端路由能力（它是构建工具 + dev server，纯前端 SPA），
   正好落在官方那句 "only when your framework doesn't provide native routing features" 之中。

→ 所以 rewrites 是 Vite SPA 在官方口径下的正确路径。**但这是依据官方口径的推断，
官方没有对 Vite 逐字明示「支持」。** 上线后建议用 preview deployment 验一次深链（见 §7）。

### 3.5 若将来需要排除某个前缀：负向断言要包在 capture group 里

`@vercel/config` 的 `RewriteRule.source` 类型注释里直接给了这个例子：

> `"/feedback/((?!general).*)"` // **Negative lookahead in a group**
> —— `node_modules/@vercel/config/dist/router.d.ts`

官方文档同一句话：

> "With `rewrites`, the regex **needs to be wrapped in a capture group**."

正确写法 `'/((?!api/).*)'`，**不是** `'/api/(!)'` 这种漏了括号的形式。

---

## 4. `VITE_API_BASE_URL`（已落地，见 `.env.example`）

`src/services/http.ts:14` 已经支持，**代码不用改**：

```ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
```

| 部署形态 | 取值 | 效果 |
|---|---|---|
| **前后端分离**（本次形态） | `https://api.epochx.net/api/v1` | 绝对地址，浏览器直接打后端，**不经过 Vercel** |
| 同域部署（后端托管前端） | **注释掉 / 删掉这一行** | 代码回落到 `/api/v1` |

### ⚠️ 陷阱：不要留空值

`VITE_API_BASE_URL=` 注入的是**空字符串 `''`**，不是 `undefined`。
而 `??` 只在 `null` / `undefined` 时兜底 —— 于是 `BASE_URL === ''`，
请求路径会**丢掉 `/api/v1` 前缀**（`/auth/me` 而不是 `/api/v1/auth/me`），**且不报任何错**。

所以「同域部署留空即用默认」这个说法**不准确**：必须是**不设置**（删掉或注释该行），而不是留空。

### 为什么分离部署下前端侧不需要 `/api` 规则

基址是绝对地址 → 浏览器直连 `api.epochx.net` → **请求根本不经过 Vercel**。
所以 Vercel 侧**不需要**为 `/api` 写任何 rewrite 或 proxy（写了也是永不触发的死规则）。
已实测确认 `vercel.ts` 产出的 rewrites 里**不含任何 `/api` 规则**（见 §5）。

**但有个未来的坑值得记在这里**：若有人把 `VITE_API_BASE_URL` 改回默认的 `/api/v1`
（例如为了本地预览方便），那么 `/api/v1/**` 就会真的打到 Vercel，
此时一条裸的 `/(.*)` 会把它回退成 `index.html` ——
**结果是 HTTP 200 + 一段 HTML**，前端 `response.ok` 为真、不抛错，
随后 `response.json()` 解析 HTML 失败才炸。表现是「接口莫名异常」而非清晰的 404/跨域报错，极难排查。

**若要防这一手**（当前不加，收益为零），把 §3.5 的配方启用即可：

```ts
routes.rewrite('/((?!api/).*)', '/index.html')
```

> 已由 lead-2 裁决：**不加**，但配方保留在本文档里。

---

## 5. 本地验证记录（**哪一次、跑了什么、结果是什么**）

> 本机无 Vercel 账号，以下全部是**本地实测**，与 §7 的「线上未验」严格分开。

| # | 验证 | 命令 / 方式 | 结果 |
|---|---|---|---|
| 1 | `vercel.ts` 真实产出 | `node --experimental-strip-types` 动态 import 该文件并打印 `config` | `{"rewrites":[{"source":"/(.*)","destination":"/index.html"}]}` —— 与官方示例**逐字一致** |
| 2 | 无 `/api` 规则 | 同上，对产出 JSON 做 `includes("/api")` | `false`（0 条 /api 规则） |
| 3 | 类型正确 | `npx tsc --noEmit --strict --moduleResolution bundler vercel.ts` | **exit 0** |
| 4 | 不破坏前端构建 | `npm run build` | **exit 0**，产物落在 `dist/` |
| 5 | 深链必然 404 | 扫 `dist/` 找路由名文件 | 匹配 **0 个**（只有 `index.html`）→ 回退必需 |
| 6 | 不被 `tsc -b` 卷进 | 读 `tsconfig.json` / `tsconfig.node.json` 的 `include` | 分别是 `src/**` 与 `vite.config.ts`，**均不含** `vercel.ts` |
| 7 | 依赖改动最小 | `git diff -- frontend/package.json` | 只增 `"@vercel/config": "0.9.0"` 一行（精确 pin，无 `^`），且位于 `devDependencies` |
| 8 | 改成 devDependencies 后回归 | `npm run build` + `node --experimental-strip-types` 重新 import `vercel.ts` | build **exit 0**；产出结构不变、仍无 `/api` 规则 |

### ⚠️ devDependencies 带来的部署侧风险（本地验不了）

`@vercel/config` 现在在 **`devDependencies`**，依据是它只在**构建/部署期**被执行
（`vercel.ts` 是配置生成器，产物里没有它的运行时代码），放 `dependencies` 会让生产依赖树多一个无关包。

**但这条依赖有个前提**：Vercel 构建时必须真的安装 devDependencies。
Vercel 默认的 install command 是 `npm install`，会装全 —— **但如果项目设置里把 install command
改成 `npm install --production`，或设了 `NODE_ENV=production`，`@vercel/config` 就不会被安装，
`vercel.ts` 会在构建期直接失败。**

→ 上线时**第一条要确认的就是这个**（见 §7 第 7 项）。本机无 Vercel 账号，无法实测。


### 第 6 项的副作用（要知道）

`vercel.ts` **不在** `tsc -b` 的检查范围内，所以 `npm run build` **不会**对它做类型检查。
本文件因此额外补了第 3 项的单独类型检查。将来若有人改这个文件，别指望 build 会报错。

---

## 6. ⏸️ 仍待补（Vercel 项目 / 域名 / 环境变量落地）

以下几节**故意留空**，等 Skyer 或拿到账号后补齐。**占位即结论，不要在此之前臆造内容。**

- [ ] **Vercel 项目创建**：怎么建、由谁建（需 Skyer 账号权限）
- [ ] **Root Directory**：应设为 `frontend`（依赖与 `build` 脚本都在 `frontend/package.json`，
      `build` = `tsc -b && vite build`，产物 `frontend/dist`）。配置口径见 §2.1，**待确认**
- [ ] **环境变量配到哪**：§4 的 `VITE_API_BASE_URL` 在 Vercel 后台的具体配法
- [ ] **自定义域名**：`epochx.net` 怎么绑到 Vercel 项目
- [ ] **Cloudflare DNS**：记录指向哪（`CNAME` 到 Vercel 分配域名 / apex 是否走代理）

### 关于 Terraform provider 的准确表述

存在第三方 Terraform provider（lead-2 核实：registry 上有 `vercel/vercel` v5.3.0，2026-05-20 发布）。
**但本项目不走该路线** —— 已定的是 `vercel.ts`。
（此前本文档写「没查到证据、别当既定事实」，那次我只查了官方文档站 URL 返回 404，
未查 registry；结论方向对但理由不完整，已更正。）

---

## 7. 未验证清单（**不要当成已实测**）

本机无 Vercel 账号，以下均**未在 Vercel 上真跑过**：

| # | 未验证项 | 状态 |
|---|---|---|
| 1 | `rewrites` 的线上实际匹配行为（含文件系统优先级） | 未验证 |
| 2 | Root Directory = `frontend` 时能否读到 `frontend/vercel.ts` | 未验证（§2.1 有官方位置口径支撑，但未实测） |
| 3 | **Vite SPA 加 rewrites 的官方逐字背书** | **官方未对 Vite 逐字明示**；§3.4 是依据官方口径的推断 |
| 4 | `vercel.ts` 是否在 Hobby 免费版可用 | 见下 |
| 5 | `epochx.net` 绑定与 Cloudflare DNS 生效 | 未验证（需域名权限） |
| 6 | 分离形态下跨域请求是否真通 | 未验证（需前后端都上线） |
| 7 | **Vercel 构建时是否安装 `devDependencies`** | 未验证。`@vercel/config` 放在 devDependencies，**若 install command 带 `--production` 或设了 `NODE_ENV=production`，它不会被安装，`vercel.ts` 构建期直接失败**。上线第一条要确认这个 |

### 关于第 4 项（`vercel.ts` 的发布阶段 / plan 限制）

**已查到的事实**（官方 changelog，`https://vercel.com/changelog/vercel-ts`，
**Published: December 19, 2025**）：

> "Vercel **now supports** `vercel.ts`, a new TypeScript-based configuration file that brings
> type safety, dynamic logic, and better developer experience to project configuration."
>
> "**All projects can now use** `vercel.ts` (or `.js`, `.mjs`, `.cjs`, `.mts`) for project configuration.
> Properties are defined identically to `vercel.json` and can be enhanced using the new
> `@vercel/config` package."

补充旁证：`/docs/project-configuration/vercel-ts` 页面**没有** `Availability` 限定标注
（同批文档里 `bunVersion` 明确标了 `> **Availability**: The Bun runtime (Beta) is available on all plans`）。

**所以判定为：未见 Beta / Preview / 付费门槛标注，且官方明写 "All projects"。**

⚠️ **但仍保留「未验证」标签**，两条理由：
1. 官方 changelog 与文档页**都没有字面写 "General Availability"** 这个词；
2. 本机无 Vercel 账号，**没有真在 Hobby 计划上建过项目**。

上线第一步建议建一个 preview deployment 顺手验掉这一条。

# api.epochx.net 的 Railway 边缘 404 — 只读定位报告（2026-11-08）

> 派单 thread：`railway-404` · 执行人：dev-4（opencode）
> 任务：只读定位 + 报告，**不修、不部署、不改任何外部配置**
> 原则：现象与推断分开；查不到就标「未定位」

## 0. 一句话结论

**后端 Railway 服务 `backend` 当前不在运行**（0/1 replicas、`deploymentStopped=true`、状态 FAILED、无 active deployment）。
域名 `api.epochx.net` **仍绑定在该服务上**，DNS 解析也指向 Railway 边缘，但 Railway 边缘找不到正在运行的服务实体，故返回 `404 Application not found`。
**生产前端 `epochx.net`（Vercel）的 `VITE_API_BASE_URL` 恰好指向这个死后端 —— 前端页面壳能加载，所有后端 API 调用全部失败。**

---

## 1. 逐条结果

### ① 服务状态：FAILED，0 replicas，无 active deployment

`railway status --json` / `railway service list --json` 原始输出：

```json
{
  "project": { "id": "28cf118d-5626-4a03-a9c3-8d26e93fac85", "name": "EpochX" },
  "environmentId": "6f20210d-bf5a-42b9-959b-fdbd4bdc832a",   // production
  "service": {
    "node": { "id": "f4934cdf-9885-4d54-a207-c9a339ccc382", "name": "backend" },
    "status": "FAILED",
    "deploymentStopped": true,
    "deploymentId": "1c0b9157-7cd9-48f9-b40e-53b35d581e7a",
    "latestDeployment": {
      "id": "1c0b9157-7cd9-48f9-b40e-53b35d581e7a",
      "status": "FAILED",
      "createdAt": "2026-10-08T15:30:59.346Z",
      "deploymentStopped": true
    },
    "replicas": { "configured": 1, "running": 0, "crashed": 0, "exited": 0, "total": 0 },
    "activeDeployments": [],
    "customDomains": [{ "domain": "api.epochx.net", "targetPort": null }]
  }
}
```

`railway status` 显示自定义域 `api.epochx.net` 绑定 id=`a99f043b-878b-47d6-bad8-3134927e79bb`，`serviceDomains: []`，`volumeInstances: []`。

**现象**：服务仍存在于 production 环境（`isLinked: true`、`restricted: false`），但**没有任何在运行的实例**。

### ② 自定义域绑定 + DNS

Railway 侧（`railway status --json`、service list 均一致）：
- `customDomains`: `api.epochx.net`（id=`a99f043b-878b-47d6-bad8-3134927e79bb`，`targetPort: null`）
- `serviceDomains`: `[]`（无自带 Railway 域名）
- Railway 环境变量里：`RAILWAY_PUBLIC_DOMAIN=api.epochx.net`、`RAILWAY_STATIC_URL=api.epochx.net`、`RAILWAY_SERVICE_BACKEND_URL=api.epochx.net`、`RAILWAY_PRIVATE_DOMAIN=backend.railway.internal`

DNS 解析（本机 `Resolve-DnsName`）：
```
api.epochx.net  CNAME  v60w072e.up.railway.app
v60w072e.up.railway.app  A  153.52.255.109
epochx.net      A      76.76.21.21
```
→ `api.epochx.net` 的 CNAME **未解绑**，仍指向 Railway 边缘（`153.52.255.109`）。`epochx.net` 指向 `76.76.21.21`（Vercel）。

**现象**：
- Railway 边缘响应：`GET https://api.epochx.net/` → `HTTP 404 {"status":"error","code":404,"message":"Application not found","request_id":...}`，响应头 `server: railway-hikari`
- `/health`、`/openapi.json`、`/api/v1/auth/me` 同样 404、同样的 `Application not found`

**推断**：Railway 边缘路由按域名找到该服务但找不到可路由的实例（服务已停止 / 已移除）——「Application not found」是 Railway 自家报错格式，**不是 FastAPI**（FastAPI 404 是 `{"detail":"Not Found"}`）。

### ③ Vercel 项目环境变量 `VITE_API_BASE_URL`

```
vercel env ls --json（项目 epochx-frontend，projectId=prj_OU3Mx1zJ9FvZDjOmgGFsBKuOpepI）
{
  "envs": [{
    "key": "VITE_API_BASE_URL",
    "value": "https://api.epochx.net/api/v1",
    "type": "plain",
    "target": ["production", "preview", "development"],
    "createdAt": 1791385564139
  }]
}
```
→ **生产前端的所有 API 请求目标都是那个死后端**。

### ④ 业务接口可达性（用上述 base）

```
GET https://api.epochx.net/api/v1/health            -> 404 {"status":"error","code":404,"message":"Application not found"}
GET https://api.epochx.net/api/v1/openapi.json      -> 404 同上
GET https://api.epochx.net/api/v1/auth/me           -> 404 同上
GET https://api.epochx.net/api/v1/chat/greeting     -> 404 同上
GET https://api.epochx.net/api/v1/me/collection/items -> 404 同上
```
对比前端域（Vercel）：
```
GET https://epochx.net/        -> 200
GET https://epochx.net/chat    -> 200
GET https://epochx.net/collection -> 200   (SPA shell 正常，内容为 HTML 壳)
```

**影响面：所有依赖后端 API 的功能全部不可用**（登录/Chat/收藏/知识库/……）。前端壳页面能打开，但任何真实数据请求都会 404。

### ⑤ 时间线

`railway logs --service backend --lines 150 --json`（read-only，按时间）：

```
2026-11-04T03:24:12Z  INFO  100.64.x.x - "GET /password/reset HTTP/1.1" 404
2026-11-04T03:24:13Z  INFO  ... "GET /auth/login HTTP/1.1" 404
... （一批 Laravel／Next 风格的扫描痕迹：/admin、/filament、/horizon、/dashboard 404）
2026-11-04T04:02:35Z  INFO  ... "GET / HTTP/1.1" 404
2026-11-04T05:42:49Z  INFO  ... "HEAD / HTTP/1.1" 405
2026-11-04T07:03:37Z  INFO  Stopping Container
2026-11-04T07:03:40Z  ERROR Shutting down / Application shutdown complete / Finished server process [1]
```

即：
- 服务在 2026-11-04 07:03:37 **被平台主动停止**（容器级，非 crash loop——「Stopping Container」而非 SIGSEGV/OOM 等）
- 停止时间与 Railway **trial 计划**用完很接近：项目创建于 2026-10-05，trial deployments 全部标注 `"plan": "trial"`
- 最后一次部署：Railway deployment list 显示 2026-10-18T15:50 的 `ba61c3e6-e2ff-450c-b650-0115fa9c5d2b`（PR #67 chat-async-frontend 合并），之后**再无部署记录**
- 代码合并至 main 的最后一条：`26794ba`（PR #93 e2e-summary-corrected）
- 期间 DNS 与 custom domain 未变，Railway 侧无 redeploy / config apply 痕迹

**推断（仅供参考）**：trial 额度用尽 → 平台停止容器（在创建 ~30 天后的 2026-11-04）。
保留该推断但**不能坐实**——我没有账单/用量接口权限，无法确认是超额还是其他原因。

---

## 2. 定性

**服务下线（容器被平台停止），域名仍绑定、DNS 未变、无人 redeploy。**

- 不是「域名解绑」—— Railway 侧 domain 状态仍 ACTIVE（绑定存在，`targetPort: null`）
- 不是「部署失败」（新构建失败）—— 没有新构建，旧容器是被**停止**的
- 是**服务不再运行**：Railway 边缘找不到活的后端实体 → 全路由 404
- 根因：**trial 计划用完导致容器被停止（推断）**，或有人手动停止——**未定位**

---

## 3. 影响面

- **后端 API 全部不可用**：登录 / Chat / 带图 / 收藏 / 错题 / 知识库 / 复盘 / 建议 / ……
- **生产前端 `epochx.net`（Vercel）功能上完全挂掉**：页面壳能开，但所有 `VITE_API_BASE_URL=https://api.epochx.net/api/v1` 的请求都 404
- 对 pilot 用户：无法登录、无法用 AI辅导、无法使用任何需要后端数据的功能
- **Neon 数据库本身没挂**：DATABASE_URL 在 Railway 变量里，指向 Neon（`soft-moon-43682197` / production / neondb）。Neon 独立于 Railway，停止容器不影响数据库本身

---

## 4. 建议修法（只列方案，不执行）

| # | 方案 | 要动什么 | 需要谁授权 | 风险/注意 |
|---|---|---|---|---|
| 1 | **升级 Railway 计划**（Hobby/Pro） | Workspace 计费计划 | Skyer | 最治本；trial 到期就是现在这种 404 |
| 2 | **确认并清理 trial 状态** | 看 Railway 账单页是否有「trial 用尽」提示、是否 pending 升级 | Skyer | 不涉及代码/域名；只恢复计费状态 |
| 3 | **redeploy 后端** | Dashboard 手动 Redeploy（build+preDeploy+deploy） | Skyer | 前提：要先有可计费的计划；否则仍会停 |
| 4 | **迁到其他平台**（Fly.io / Render / 自建 VPS） | 迁移 IaC/变量/域名 | Skyer | 成本/时间成本大；API 域名/Neon 都可迁；pilot 阶段可能不值得 |
| 5 | **把前端的 VITE_API_BASE_URL 改指向可用后端** | Vercel 环境变量 | Skyer | 前端现在也没有任何可用后端，改了也没用，除非先有备份实例 |
| 6 | **临时发一个免费后端**（Render free 等）作为降级 | 新建服务+部署 | Skyer | 需注意数据/合规（Neon 共享），pilot 口径下可由 Skyer 定 |

**不推荐自行 redeploy 或做任何改动**——任务边界是「只读定位」，且任何外部动作（redeploy/域名/变量/计费）都必须 Skyer 明确授权。

---

## 5. 不确定 / 待确认

- trial 计划用完导致停止是**推断**——无法用 CLI 核实计费原因，需要 Skyer 看 Railway 账单确认（是否有到期/超额提示）
- Railway 侧是否存在「scheduled sleep」或其它停机机制，CLI 输出未显示，无法确认
- Neon 数据是否在 Railway 停止期间被任何维护操作影响——未核实（不在本单范围）

---

## 附：测试/数据来源

- `railway` CLI 5.63.1（2026-11-08 08:0x 本机），已 `railway login`（dumpSS）
- `vercel` CLI 62.2.0（epochx-frontend 项目，已 link）
- DNS：本机 `Resolve-DnsName`
- HTTP：本机 `Invoke-WebRequest` / `curl` 风格裸探测
- 未做任何写操作：未 redeploy、未改域名绑定、未改变量、未改 Vercel 配置

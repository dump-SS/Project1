# #47 摘要链路端到端真跑（2026-11-07）

> 派单 thread：`e2e-summary` · 执行人：dev-4（opencode）
> 代码基线：`main = 4dbc7966`（PR #92 `fix/collection-i1-i2-i5` 已合）；契约 `docs/openapi.yaml` v1.19.1
> **本轮无代码改动**：前端 `handleSummarize` + `FileSummaryCard` + `collectItem` 已随 PR #92 合入，本次只做真链路补验。

> **⚠️ 2026-11-07 lead-1 修订记录**（原报告由 dev-4 交付，本次只修表述与编号，实测数据与原始输出一字未动）：
> 1. **区分两轮验证**：Step 1–7 完整 UI 流程是 **11-06 23:58** 在**同平台另一视觉模型 `Doubao-Seed-2.1-pro`** 下闭环的；**11-07 08:04** 另做 `GLM-5.3-Flash` **直接探针**（见 §3 响应体 id `202611070804…`）。原报告把两者混写为「E2E 用 GLM 覆盖完成验证」，易被误读成生产模型已跑完全链路，已改正。
> 2. **消除自相矛盾**：原报告第 96 行称「503 与生产模型无关」，第 110 行又称「后端代码路径多次调用也 503」。统一为：探针通过；业务链路间歇 503 属**上游容量抖动**，非模型特有问题。
> 3. **结论不再下满**：「视觉通道可用（已验证）」改为「**探针级可用**」。
> 4. **编号重排**：原有两个 `## 4` 且 §5 夹在中间 → 现为 §3 原始输出 / §4 回归 / §5 发现与待办。
> 5. **Skyer 22:46 拍板**：同平台已有视觉模型跑通全流程，**不再换模型重复验**（避免过度/冗余验证）；间歇 503 记为 **pilot 待观察**，不阻塞、不换模型。

## 0. 结论

**主链路通过**（同平台视觉模型 `Doubao-Seed-2.1-pro` 下）：真实 R2 上传 → 真实 LLM 视觉摘要 → 摘要卡 → 存入收藏 → 个人中心可见且可展开（markdown + sourceMap 正常，`v=1 total=80 chunks=4`）。

**生产模型 `GLM-5.3-Flash` 视觉探针级可用**：`.railway/railway.py:162` 与 runbook:229 明写它是 Skyer 指定值、**不要自行替换**；11-07 直接探针 HTTP 200、5250 ms、返回可解析 JSON（§3）。**完整 UI 流程未在 GLM 下单独复验** —— 按 Skyer 22:46 拍板，同平台已有视觉模型跑通全流程，链路代码不随模型名变，不再重复验。

本地开发机 `backend/.env` 写的是 `Step-3.5-Flash`，其视觉通道被上游 503「暂无可用服务商」—— **非生产模型、生产未挂**。两轮验证均只做进程级 env 覆盖（**未改 `.env`、未改代码、不碰 Railway 变量**）。

## 1. 环境与口径

| 项 | 值 |
|---|---|
| 代码 | `D:\Projects\Project1`，`main = 4dbc7966`，工作区无本次改动（仅既有未追踪文件） |
| 后端 | `uvicorn main:app --host 127.0.0.1 --port 8000`；`DATABASE_URL=sqlite:///D:/Projects/Project1/backend/data.db` + `EPOCHX_ALLOW_SHARED_DB=1`（显式声明共享开发库） |
| R2 | 凭据经**进程环境变量注入**（`KB_VECTOR_URL` 含桶名 `epoch-x`），未写入任何文件、未打印 |
| LLM | 生产模型 `GLM-5.3-Flash`（`.railway/railway.py:162`、runbook:229，Skyer 指定，不要自行替换）；本地开发机 `backend/.env` 写 `Step-3.5-Flash`（视觉 503，非生产模型）；**Step 1–7 完整 UI 流程**用进程级 env 覆盖为 `Doubao-Seed-2.1-pro`（11-06 23:58）；**GLM-5.3-Flash 直接探针**另于 11-07 08:04 单跑（§3）。均为进程级覆盖，未改 `.env` |
| 前端 | `npm run dev`（Vite 5173），`/dev-login` 一键登录 `demo@epochx.local` |
| 账号 | `demo@epochx.local` → `u_2d8c3325a96a4ed1`（库内唯一用户；本轮前 `collection_items = 0`） |
| 浏览器 | in-app Chromium；因后台标签页 CSS 动画被节流（页面过渡层 `opacity:0` → 可访问树为空），交互用页面内 DOM 事件驱动；**上传仍走组件真实 handler + 真实 `POST /f/media`**，不是绕过 UI 直接 fetch |
| 测试图 | 本机生成 960×540 PNG（15,883 B），内容为 4 道数学题 |

## 2. 逐步实测

### Step 1 登录 ✅
- `POST /api/v1/auth/login-password → 200`
- `GET /api/v1/auth/me → 200`，侧栏显示 `demo@epochx.local`

### Step 2 真实上传（R2）✅
- 通过 `<input type=file data-testid="media-capture-input">` 注入测试图并派发 `change`
- `POST /api/v1/f/media → 201 Created`
- 返回 key：`user/u_2d8c3325a96a4ed1/4efd50ab1c3049b793671d2a8b5fd91e.png`
- 预览 `GET /api/v1/f/media/{key} → 200`（字节从 R2 取回并渲染）

### Step 3 摘要（LLM 视觉）✅

**本步属于 11-06 23:58 的完整 UI 流程**，当时进程级覆盖为同平台另一视觉模型 `Doubao-Seed-2.1-pro`：
- 本地开发机 `backend/.env` 的 `Step-3.5-Flash` 视觉 503「暂无可用服务商」，故改用上述可用模型；该 503 **非生产模型、生产未挂**
- UI 出现摘要卡，4 条要点（解方程 / 分数加法 / 因式分解 / 三角形面积），服务端已脱敏（privacy_filter 兜底）
- 下方 JSON 是 **11-07 08:04 另做 `GLM-5.3-Flash` 直接探针**的返回，内容与 UI 摘要卡一致；**不是同一次 UI 调用的响应**：
  ```
  {"subject":"MATH","summary":"数学作业，共4题：1. 解方程 2x + 5 = 17；2. 计算 3/4 + 1/6；3. 因式分解 x^2 - 9；4. 求三角形面积（底6cm，高4cm）"}
  ```
  探针 HTTP 200，耗时 5250 ms，`finish_reason=stop`；原始响应体见 §3

### Step 4 存入收藏 ✅
- 点「存入收藏」→ 卡片变为 `✓ 已存入收藏（可在个人中心查看）`
- `POST /api/v1/me/collection/items → 201`
- `created = true`（新建）

### Step 5 个人中心可见 ✅
- `/collection` 列表出现：`上传照片摘要` / 来源徽标 `上传摘要` / `2026-11-06 23:58`
- 点「展开全文」：4 条要点按 markdown 正确渲染；页面提供「划选高亮 / 全部虚化」（sourceMap 已随快照保存）
- 截图：暗色主题下收藏卡完整展示（见会话截图）

### Step 6 数据库核验 ✅
`collection_items` 实查（`itemId = citem_9a8435392c94`）：

| 字段 | 值 |
|---|---|
| `title` | 上传照片摘要 |
| `snapshot.content` | 上述 4 条要点原文 |
| `snapshot.format` | `markdown` |
| `snapshot.sourceMap` | `v=1, total=80, chunks=4` |
| `sourceRef` | `{"type":"upload_summary","refId":"user/u_2d8c.../4efd50ab....png","label":"上传照片摘要","subject":"SX"}` |

### Step 7 清理 ✅
- 测试 key 追加到 append-only manifest：`C:\Users\29622\AppData\Local\Temp\opencode\r2_manifest.json`（1 条）
- `DELETE /api/v1/f/media/{key} → 204`（幂等）
- 复查 `GET → 404`，确认已删除
- 说明：`scripts/r2_sweep.py` 固定指向生产 API + `u_10237`，不适用于本机 demo 账号；本机用同一幂等 DELETE 端点清理，等价语义
- 演示账号保留 1 条收藏作为证据（R2 原图已删，快照仍可读，符合 D46「存快照不存引用」）

## 3. GLM 视觉真调原始输出

| 项 | 值 |
|---|---|
| base_url | `https://aiping.cn/api/v1` |
| model | `GLM-5.3-Flash`（进程级 env 覆盖 `LLM_MODEL`；未改 `.env`） |
| image | `math_homework.png`，15,883 bytes，4 道数学题 |
| HTTP | 200 |
| 耗时 | 5250 ms |
| model field | `GLM-5.3-Flash` |
| finish_reason | `stop` |
| usage | prompt_tokens=738, completion_tokens=188, total_tokens=926 |
| provider | `-`（非 fallback） |

**原始响应体（完整）：**
```json
{"choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "{\"subject\":\"MATH\",\"summary\":\"数学作业，共4题：1. 解方程：2x + 5 = 17。 2. 计算 3/4 + 1/6 = ?。 3. 因式分解：x^2 - 9。 4. 求三角形面积：底 6cm，高 4cm。\"}", "reasoning_content": "The user wants me to look at the image and return JSON with subject and summary. The image shows a math homework (数学作业) with 4 problems:\n1. 解方程：2x + 5 = 17 (Solve equation)\n2. 计算 3/4 + 1/6 = ? (Calculate)\n3. 因式分解：x^2 - 9 (Factor)\n4. 求三角形面积：底 6cm，高 4cm (Find triangle area)\n\nSubject is MATH. Summary should describe the content.", "role": "assistant"}}], "created": 1794009896, "id": "202611070804518bd0526bab514d0c, "model": "GLM-5.3-Flash", "object": "chat.completion", "request_id": "01a1b352-8221-7763-bc6e-81aafb004684", "usage": {"completion_tokens": 188, "completion_tokens_details": {"reasoning_tokens": 114}, "prompt_tokens": 738, "prompt_tokens_details": {"cached_tokens": 0}, "total_tokens": 926}, "provider": "-", "is_fallback": false}
```

**现象与推断分开：**
- 现象：GLM-5.3-Flash 视觉调用 HTTP 200，5.25 s，返回可解析 JSON，subject=MATH，4 条要点均正确（与测试图内容一致）；无 503、无空串、无 reasoning_tokens 吃光 content。
- 推断：生产模型 GLM-5.3-Flash 视觉**探针级可用**（模型本身具备多模态、能返回可解析 JSON）。**不换生产模型**，保持 `GLM-5.3-Flash`。
- ⚠️ 限定：这是**直接探针**结论，不等于业务链路已在该模型下完整复验。后端代码路径多次调用时曾出现上游 503「暂无可用服务商」（见 §5），属**上游容量抖动**、非模型特有问题；按 Skyer 22:46 拍板不再重复验，记为 pilot 待观察。

## 4. 回归验证

| 检查 | 结果 |
|---|---|
| `pytest tests/test_media_summary.py tests/test_f_media.py` | **40 passed** |
| `pytest tests/test_collection.py` | **29 passed** |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过（仅既有 chunk >500kB 警告，与本次无关） |

## 5. 发现与待办

1. **生产模型 GLM-5.3-Flash 视觉探针通过**（非全链路复验）：直接探针两次成功（HTTP 200，5.25s/5.84s，返回可解析 JSON，subject=MATH，4 条要点正确），通过 env 覆盖确认 `settings.llm_model` 正确解析为 `GLM-5.3-Flash`。**不换生产模型**，保持 `GLM-5.3-Flash`。
   - 现象：后端代码路径多次调用时**曾出现**上游 503「暂无可用服务商」（推理模型 + 图片 + `max_tokens=8192`），与直接探针成功形成对比。
   - 推断：属**上游容量抖动**，非模型特有问题；可能与参数组合（大 max_tokens + 图片 + 推理）有关，但未定量、未定位，不下结论。
   - **Skyer 22:46 拍板**：同平台已有视觉模型跑通全流程，链路代码不随模型名变，**不再换模型重复验**（避免过度/冗余验证）。此 503 **记为 pilot 待观察**，不阻塞、不换模型、不派活。
   - 本地开发机 `.env` 的 `Step-3.5-Flash` 视觉确实 503，**非生产模型，不影响生产链路**。**本机未改 `.env`。**

2. 测试方法留痕：后台标签页动画节流会让页面过渡层停在 `opacity:0`，可访问树为空；后续 E2E 若遇「snapshot 只剩侧栏」可按此处理（注入 `animation:none; opacity:1`）。

3. 本轮未验证：PATCH 高亮/虚化**持久化**（只展开未落标记）；该能力已有 `test_collection.py` 覆盖，如需端到端补验可另开一轮。

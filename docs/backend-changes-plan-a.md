# 方案A：导学推荐 后端需补的改动说明

> **归档说明（2026-08-29 补记）**
>
> 本文档为历史快照，其阶段口径按当时的**正式发布尺度**书写（含「法务评审」「上线门硬前置」等要求），**不代表当前 pilot 口径，请勿据此安排工作**。
>
> 项目当前处于 pilot 阶段，由学生团队维持，无外部评审资源。现行阶段口径见仓库根目录 `PRD-学习状态智能助手.md` 文首「关于阶段口径」一节。

> 状态：仅说明，未对后端做任何改动。
> 范围：配合前端已落地的「StudyGuide（导学计划）」+「StudyPlanEditor（学习计划编辑）」方案A实现。
> 决策来源：队友 review 反馈的 #1/#2/#3 三条整改项（时间输入改格式、接入生成计划、推荐学科去硬编码），其中方案A 走"POST /plans 取 tasks[0].topic 作为推荐"路线。

## 1. 方案A 在前端已长什么样

落地在 `frontend/src/pages/StudyGuide/index.jsx` 与 `frontend/src/pages/StudyPlanEditor/index.jsx`，关键点：

1. **时间输入改格式**：`StudyEditor` 用 `inputType="number"`，`MINUTES_VALIDATOR` 校验 10-600 的整数，**不再**接受"12:30"时钟字符串。
   请求体：`{ planDate, availableMinutes: <int 10..600> }` → `POST /plans`。
2. **接入生成计划**：点「进入」第一次点击同步调 `POST /plans`，成功后留在本页面渲染 `TaskList`；第二次点「进入」才放行跳转 `/study-timer`。本地有 `plan:last` 缓存做离线降级。
3. **推荐学科去硬编码**：删掉原 `DEFAULT_SUBJECT` 常量，改成
   ```js
   const first = created.tasks?.[0]
   if (first) {
     const label = subjectLabels[first.subject] ?? first.subject
     setRecommendation(`${label} · ${first.topic}`)
   }
   ```
   即「学科中英文 + topic」。AUTO 按钮把这个字符串写进「学习任务编辑」文本框。

> 结论：**契约侧不需要新加接口**，方案A 完全在现有 `POST /plans` 的响应结构内可走通。
> 但要让推荐质量稳定、刷新页面后仍能复用，需要后端做几项**实现侧**的补强（见下）。

## 2. 后端需要补的改动（按优先级）

### P0 · `POST /plans` 实现补强

| # | 改动点 | 说明 | 影响 |
|---|---|---|---|
| P0-1 | **保证 `tasks` 至少 1 条** | 当前契约未强制非空。当用户无学科、无目标、无历史记录时，规则引擎可能返回空 `tasks`，前端推荐会显示「填写学习分钟后点击进入…」。需要兜底为 1 条通用任务（如 "通用学科 · 自由学习"）。 | 推荐永远有内容，AUTO 才有可填值 |
| P0-2 | **`tasks[0].topic` 必须对用户可读** | 契约只写"内容方向，颗粒度到「学科 + 方向」"。前端会原样塞进推荐文本框，topic 太抽象（如 `math · unit_3`）会让推荐不可用。建议落地为「学科中方向 + 一句具体说明」，例 `数学 · 函数图像与性质 · 巩固已学`。 | 直接决定推荐可读性 |
| P0-3 | **`tasks[0].subject` 必须是合法 `Subject` 枚举** | 前端用本地 `subjectLabels[subject]` 做中英文映射，找不到就退化到原始 enum 值。后端要保证 `subject ∈ {chinese, math, english, physics, chemistry, biology, history, geography, politics, other}`，不出现自定义值。 | 避免推荐文本出现裸 enum |
| P0-4 | **同步重算的窗口要拉够** | `adaptedFrom` 是基于最近一次状态评估做强度调整。当用户刚提交过学习记录、`stateLabel=insufficient_data` 时，规则引擎也应当按"新用户"模板生成，不要因为评估空就拒生。 | 新用户冷启动必须能拿到计划 |

### P1 · 持久化推荐（页面刷新后仍能复用）

现状：方案A 把推荐放在 React 内存里，刷新就丢。要支持刷新后仍可看，需要**重新拉一次今天的计划**，从中再派生推荐。

后端两种实现路径（任选其一即可，前端都能配合）：

- **路径 A（推荐，无新接口）**：复用现有 `GET /plans?dateFrom={today}&dateTo={today}`，前端进入页面时先 GET 一次，命中今日计划就用 `items[0]` 派生推荐，避免重新生成。
  - 后端**零改动**，只要求 `GET /plans` 列表能按 `dateFrom/dateTo` 精确命中单日。
- **路径 B（可选，新增便捷接口）**：新增 `GET /plans/today`，语义等价于「取今日最近一份计划」，未生成则返回 404。
  - 需要在 `openapi.yaml` 加一条 path，并在 `api-design-unified.md` 第 2.1 节补描述。
  - 若走此路径，请同步告知前端组，前端会在 `StudyGuide/index.jsx` 加一个 `useEffect` 进入即拉取。

> 选 A 还是 B 由后端组拍板。前端会按后端实际给的方案调整，不在这里强约束。

### P2 · 错误码与边界（建议但非阻塞）

| 场景 | 建议 | 备注 |
|---|---|---|
| `POST /plans` 同日重复 | 保持现有 409 + `regenerate=true` 机制 | 前端目前会显式捕获 409 并提示 |
| `PlanCreate.goalIds` 传入已归档目标的 ID | 建议服务端静默过滤 + 响应回 201 | 避免前端需要单独清理 |
| `PlanCreate.availableMinutes` 越界 | 维持 400 `VALIDATION_FAILED` | 前端校验已做，但服务端兜底必填 |
| `POST /plans` 超时 | 建议增加 5s 内超时即返回降级（不带 LLM，走纯规则） | 同步接口必须可预期时长 |

## 3. 不需要改的地方（明确豁免，避免后端误改）

- **`POST /plans` 请求/响应 schema**：不动。`PlanCreate` 的 `planDate` / `availableMinutes` / `goalIds?` / `regenerate?` 已经覆盖方案A 全部入参。
- **`PlanTask.topic` 字段定义**：不动。粒度由 P0-2 在实现侧补强。
- **`Subject` 枚举**：不动。前端用本地 `subjectLabels` 做中英文映射，无需后端做 i18n。
- **`Recommendation` / `RecScene`**：不动。方案A 走规则引擎，不走 LLM，`/recommendations/*` 全部跳过。
- **`/recommendations` 任意扩展**：方案A 明确**不**接 LLM 推荐，不需要新增 `RecScene = pre_session` 之类的场景。等真要接 LLM 时再单独开讨论。

## 4. 验收清单（请后端组在合并前自测）

完成后请按以下场景在 Swagger UI 或 Postman 跑通：

1. **冷启动**（新用户、无学科、无目标、无记录）：
   - `POST /plans` 返回 201，`tasks.length ≥ 1`，`tasks[0].subject ∈ Subject`，`tasks[0].topic` 是一句可读中文。
   - `adaptedFrom === null`。
2. **有目标**（创建 1 个 short_term 目标后）：
   - `POST /plans` 至少返回 1 条 `goalId === <新建目标>` 的任务。
3. **有历史记录**（提交过 2 条以上学习记录后）：
   - `POST /plans` 的 `adaptedFrom` 非空，`stateLabel` 对得上最近一次 `GET /assessments/current`。
4. **同日重复**：
   - 不带 `regenerate=true` 第二次 `POST /plans` 返回 409 `STATE_CONFLICT`。
   - 带 `regenerate=true` 返回 201，新 `planId`。
5. **`availableMinutes` 越界**（填 5 或 700）：返回 400 `VALIDATION_FAILED`。
6. **`GET /plans?dateFrom=today&dateTo=today`**：能精确返回今日那份计划（含 P1 路径 A 验收）。

## 5. 与前端 PR 的解耦说明

- 前端已在 `feature-Jacky-Page2` 分支落地方案A，**对后端实现无强依赖**：
  - 网络层走 mock-server 联调，接口契约对得上即可。
  - 真实后端实现是 P0 表格里的"建议"而非"必须"，不阻塞前端 PR 合并。
- 真正接真实后端前，前端会保留 `subjectLabels` 兜底与 `plan:last` localStorage 缓存，避免后端 topic 暂未优化时体验崩。
- 后端如对 P0-1/P0-2/P0-3 有不同实现策略（例如改 `subjectLabels` 由后端下发），请单独同步，前端会按需加适配。

---

附录：
- 涉及的 OpenAPI 章节：`openapi.yaml` 第 2.1 节 `createPlan` / `Plan` / `PlanTask`。
- 涉及的设计文档章节：`api-design-unified.md` 第 2.1 节「学习计划」。
- 前端关联文件：
  - `frontend/src/pages/StudyGuide/index.jsx`
  - `frontend/src/pages/StudyPlanEditor/index.jsx`
  - `frontend/src/services/plans.ts`

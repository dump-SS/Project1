# RESTful API 设计 · 统一版（板块一 · 中学学情导学与状态评估）

- 对应需求：`PRD-学习状态智能助手-v1.3.md`
- 整合来源：`api-design-mvp.md`（v1）与 `api-design-mvp-v2.md`（v2），取两版优点合并统一，本文档为唯一生效版本
- 覆盖主流程：**创建目标 → 生成计划 → 提交学习记录 → 计算状态 → 返回建议**（外加周期复盘与反馈回路）

---

## 0. 通用约定

### 0.1 基础约定

| 项目 | 约定 |
|---|---|
| 基础路径 | `/api/v1`，下文所有 URL 均省略此前缀 |
| 鉴权 | `Authorization: Bearer <token>`；MVP 不设计登录/注册接口，假定已有账号体系 |
| 传输格式 | `application/json; charset=utf-8` |
| 时间 | ISO 8601 带时区，如 `2026-08-16T20:30:00+08:00`；纯日期用 `2026-08-16` |
| 命名 | 路径用复数名词，字段用 camelCase |
| 分页 | query 参数 `page`（默认 1）、`pageSize`（默认 20，上限 50）；列表响应固定为 `items` + `pagination` |
| 幂等 | 写接口可选携带 `Idempotency-Key` 头，24 小时内重复键直接返回首次结果（用于弱网下重复提交学习记录） |
| 资源作用域 | 所有资源以当前 token 用户为作用域，不设 `userId` 路径参数，不存在跨用户读取接口 |

### 0.2 统一错误格式

成功响应直接返回资源对象或集合，不做额外包裹。失败统一为：

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "自评专注度必须为 1-5 的整数",
    "field": "selfReport.focus"
  }
}
```

| HTTP 状态 | 错误码示例 | 场景 |
|---|---|---|
| 400 | `VALIDATION_FAILED` | 参数缺失或取值越界 |
| 401 | `UNAUTHENTICATED` | token 缺失或过期 |
| 403 | `GUARDIAN_AUTHORIZATION_EXPIRED` | 监护人授权失效，账号只读（PRD 8.1），仅 GET 可用 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在或不属于当前用户 |
| 409 | `STATE_CONFLICT` | 如同一日期重复生成计划 |
| 429 | `RATE_LIMITED` | 手动触发 AI 生成超频（PRD 6.4 控成本） |
| 500 | `INTERNAL_ERROR` | 服务端错误 |

### 0.3 AI 异步生成约定（PRD 6.4）

建议、复盘两类资源涉及大模型调用，统一为「创建即返回句柄，内容后到」：

- `POST` 创建 → `202 Accepted`，返回资源 id 与 `generation.status = "pending"`
- 前端轮询 `GET` 该资源获取结果
- 终态：`ready`（`source` 标明 `llm` / `template`）、`insufficient_data`、`failed`
- 建议类资源在 LLM 失败时自动降级为模板兜底并仍返回 `ready`，响应结构不变，前端无需分支处理（PRD 5.3）
- 复盘不做模板兜底，失败即 `failed`，提示稍后再试（PRD 5.4 不展示半成品）

### 0.4 枚举字典

| 枚举 | 取值 |
|---|---|
| `subject` | `chinese` `math` `english` `physics` `chemistry` `biology` `history` `geography` `politics` `other` |
| `stage` | `junior`（初中）`senior`（高中） |
| `goalType` | `short_term` `long_term` |
| `taskStatus` / `completion` | `pending` `completed` `partial` `abandoned`（completion 无 `pending`） |
| `emotion` | `positive` `neutral` `negative` |
| `difficultyFeel` | `easy` `moderate` `hard` |
| `trend` | `up` `flat` `down` |
| `stateLabel` | `efficient_stable` `fatigue_warning` `emotion_blocked` `fluctuating_up` `insufficient_data` |
| `recScene` | `post_session`（单次学习后）`weekly_review`（阶段回顾） |
| `source` | `llm` `template` |
| `rating` | `useful` `neutral` `not_useful` |

---

## 1. 用户与设置

### 1.1 获取当前用户资料

| 项 | 内容 |
|---|---|
| URL | `/me` |
| 方法 | `GET` |
| 说明 | 前端据此判断是否需要引导建档 |

响应 `200`：

```json
{
  "userId": "u_10237",
  "stage": "senior",
  "grade": "高二",
  "subjects": ["math", "english", "physics"],
  "guardianAuthorization": { "status": "active", "expiresAt": "2026-09-10T00:00:00+08:00" },
  "onboardingCompleted": true
}
```

### 1.2 初始化 / 更新用户资料

| 项 | 内容 |
|---|---|
| URL | `/me` |
| 方法 | `PUT`（幂等建档，字段全必填）/ `PATCH`（局部更新，字段全可选） |

| 字段 | 类型 | 必填(PUT) | 说明 |
|---|---|---|---|
| stage | string(enum) | 是 | `junior` / `senior` |
| grade | string | 是 | 年级，如 `"初二"`、`"高二"` |
| subjects | string[] | 是 | 学科枚举数组，1-9 项 |

响应 `200`：同 1.1 的用户对象。

### 1.3 读取 / 更新设置

| 项 | 内容 |
|---|---|
| URL | `/me/settings` |
| 方法 | `GET` / `PATCH` |
| 说明 | 承载 PRD 5.2「关闭 AI 自动调权」与 6.2「不发送我的文字内容」两个必须开关 |

PATCH 请求参数（至少传一项）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| aiWeightTuningEnabled | boolean | 否 | 默认 `true`；关闭后固定使用默认权重 |
| sendTextToAI | boolean | 否 | 默认 `false`；关闭时目标描述等自由文本不出域，仅用结构化特征生成 |

响应 `200`：

```json
{
  "aiWeightTuningEnabled": true,
  "sendTextToAI": false,
  "updatedAt": "2026-08-16T09:12:00+08:00"
}
```

> 权重数值（α、β 及各子权重）不通过任何用户侧接口暴露（PRD 5.2）。

### 1.4 监护人授权（合规底线，PRD 8.1）

| URL | 方法 | 说明 |
|---|---|---|
| `/me/guardian-authorization` | `POST` | 提交监护人邮箱/手机号（二选一必填），发送确认请求，响应 `202` |
| `/guardian-authorization/confirm?token=xxx` | `GET` | 监护人点击链接确认，无需登录 |
| `/me/guardian-authorization` | `DELETE` | 撤销授权，账号进入只读，响应 `204` |

POST 请求参数：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| guardianEmail | string | 二选一 | 监护人邮箱 |
| guardianPhone | string | 二选一 | 监护人手机号 |

> 授权失效时所有写接口返回 `403` + `GUARDIAN_AUTHORIZATION_EXPIRED`，读接口不受影响。

---

## 2. 学习目标 Goals

目标独立成资源：一个用户可同时持有多个短/长期目标，计划生成按 `goalId` 引用。

### 2.1 创建目标 ①

| 项 | 内容 |
|---|---|
| URL | `/goals` |
| 方法 | `POST` |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| type | string(enum) | 是 | `short_term` / `long_term` |
| subject | string(enum) | 是 | 所属学科，跨学科目标填 `other` |
| title | string | 是 | ≤50 字，如「两周后期中考试数学 120+」 |
| description | string | 否 | ≤200 字自由文本，出域受 `sendTextToAI` 控制 |
| targetDate | string(date) | 否 | 短期目标建议必填 |
| templateId | string | 否 | 从预设模板创建时带上 |

响应 `201`：

```json
{
  "goalId": "g_5501",
  "type": "short_term",
  "subject": "math",
  "title": "两周后期中考试数学 120+",
  "description": "函数和数列这两章不太熟，想重点补",
  "targetDate": "2026-08-30",
  "status": "active",
  "progress": { "plannedTasks": 0, "completedTasks": 0, "ratio": 0 },
  "createdAt": "2026-08-16T09:20:00+08:00"
}
```

### 2.2 目标列表

| 项 | 内容 |
|---|---|
| URL | `/goals` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| status | string | 否 | `active`（默认）/ `archived` / `all` |
| subject | string(enum) | 否 | 按学科过滤 |
| page / pageSize | integer | 否 | 分页 |

响应 `200`：

```json
{
  "items": [
    {
      "goalId": "g_5501",
      "type": "short_term",
      "subject": "math",
      "title": "两周后期中考试数学 120+",
      "targetDate": "2026-08-30",
      "status": "active",
      "progress": { "plannedTasks": 12, "completedTasks": 7, "ratio": 0.58 }
    }
  ],
  "pagination": { "page": 1, "pageSize": 20, "total": 3 }
}
```

### 2.3 更新 / 归档目标

| 项 | 内容 |
|---|---|
| URL | `/goals/{goalId}` |
| 方法 | `PATCH` |
| 说明 | 归档代替删除，保留历史数据供复盘引用 |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| title | string | 否 | |
| description | string | 否 | |
| targetDate | string(date) | 否 | |
| status | string | 否 | `active` / `archived` |

响应 `200`：完整目标对象（同 2.1）。

---

## 3. 学习计划 Plans

对应 PRD 5.1。`POST /plans` 语义是「请求生成一份计划」，服务端规则引擎结合最近一次状态评估决定任务强度，**同步返回**，不走 LLM（PRD 8.2：AI 不可用时仍能看计划）。

### 3.1 生成计划 ②

| 项 | 内容 |
|---|---|
| URL | `/plans` |
| 方法 | `POST` |
| 说明 | 同一 `planDate` 已有计划时返回 `409`，可传 `regenerate=true` 覆盖 |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| planDate | string(date) | 是 | 计划归属日期 |
| availableMinutes | integer | 是 | 本次可用学习时间，10-600 分钟 |
| goalIds | string[] | 否 | 关联目标，不传则使用全部 active 目标 |
| regenerate | boolean | 否 | 默认 `false`；`true` 覆盖当日已有计划 |

响应 `201`：

```json
{
  "planId": "p_9001",
  "planDate": "2026-08-16",
  "availableMinutes": 120,
  "adaptedFrom": {
    "assessmentId": "a_7742",
    "stateLabel": "fatigue_warning",
    "adjustment": "reduce_load",
    "note": "最近状态偏疲劳，本次总时长下调，单任务时长缩短并增加间隔"
  },
  "tasks": [
    {
      "taskId": "t_30011",
      "subject": "math",
      "topic": "函数图像与性质 · 巩固已学",
      "estimatedMinutes": 40,
      "priority": 1,
      "status": "pending",
      "goalId": "g_5501"
    },
    {
      "taskId": "t_30012",
      "subject": "english",
      "topic": "单词短时高频复习",
      "estimatedMinutes": 20,
      "priority": 2,
      "status": "pending",
      "goalId": null
    }
  ],
  "createdAt": "2026-08-16T18:00:00+08:00"
}
```

> 新用户无历史数据时 `adaptedFrom` 为 `null`，走规则模板生成（PRD 5.1 处理逻辑第 1 条）。

### 3.2 计划列表 / 详情

| URL | 方法 | 参数 | 说明 |
|---|---|---|---|
| `/plans` | `GET` | `dateFrom` / `dateTo`（可选，默认最近 7 天）、`page` / `pageSize` | 列表 |
| `/plans/{planId}` | `GET` | — | 详情，结构同 3.1 |

### 3.3 调整任务 / 确认完成

| 项 | 内容 |
|---|---|
| URL | `/plans/{planId}/tasks/{taskId}` |
| 方法 | `PATCH` |
| 说明 | 改时长、删任务、标完成度都走这里；每次调整记为算法反馈信号（PRD 5.1 交互要点） |

请求参数（至少传一项）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| estimatedMinutes | integer | 否 | 用户手动改时长 |
| status | string(enum) | 否 | `pending` / `completed` / `partial` / `abandoned` |
| removed | boolean | 否 | `true` 表示删除该任务（软删除，保留反馈信号） |

响应 `200`：

```json
{
  "taskId": "t_30011",
  "subject": "math",
  "topic": "函数图像与性质 · 巩固已学",
  "estimatedMinutes": 30,
  "priority": 1,
  "status": "partial",
  "removed": false,
  "userAdjusted": true,
  "updatedAt": "2026-08-16T21:05:00+08:00"
}
```

---

## 4. 学习记录 Learning Records

### 4.1 提交学习记录（核心接口）③④

| 项 | 内容 |
|---|---|
| URL | `/learning-records` |
| 方法 | `POST` |
| 说明 | 行为数据 + 10 秒内可完成的自评一次性提交。状态分是确定性规则计算（PRD 5.2），**同步重算并在响应中带回状态快照**；同时自动创建一条 `post_session` 建议生成任务，返回其 `recommendationId`（pending），前端拿着它去 6.2 轮询即可 |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| subject | string(enum) | 是 | 状态按学科分开评估，故必填 |
| startedAt | string(datetime) | 是 | 学习开始时间 |
| durationMinutes | integer | 是 | 实际学习时长，1-600 |
| planTaskId | string | 否 | 关联计划任务；自由学习可不传（PRD 7 允许可空） |
| behavior | object | 是 | 行为数据 |
| behavior.completion | string(enum) | 是 | `completed` / `partial` / `abandoned` |
| behavior.accuracy | number | 否 | 正确率 0-1；无客观测验时不传，服务端将该项权重归零重分配 |
| behavior.interruptions | integer | 否 | 中断次数，默认 0 |
| behavior.blurCount | integer | 否 | 页面失焦次数（小程序弱信号），客户端自动采集 |
| selfReport | object | 是 | 自评数据 |
| selfReport.focus | integer | 是 | 专注度 1-5 |
| selfReport.fatigue | integer | 是 | 疲劳度 1-5 |
| selfReport.emotion | string(enum) | 是 | `positive` / `neutral` / `negative` |
| selfReport.difficultyFeel | string(enum) | 是 | `easy` / `moderate` / `hard` |
| note | string | 否 | ≤100 字备注，出域受 `sendTextToAI` 控制 |
| skipRecommendation | boolean | 否 | 默认 `false`；`true` 时不自动生成建议 |

请求示例：

```json
{
  "subject": "math",
  "startedAt": "2026-08-16T19:00:00+08:00",
  "durationMinutes": 45,
  "planTaskId": "t_30011",
  "behavior": { "completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5 },
  "selfReport": { "focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard" },
  "note": "函数图像那块看不太进去"
}
```

响应 `201`：

```json
{
  "recordId": "r_88012",
  "subject": "math",
  "startedAt": "2026-08-16T19:00:00+08:00",
  "durationMinutes": 45,
  "planTaskId": "t_30011",
  "behavior": { "completion": "partial", "accuracy": 0.62, "interruptions": 3, "blurCount": 5 },
  "selfReport": { "focus": 2, "fatigue": 4, "emotion": "negative", "difficultyFeel": "hard" },
  "assessment": {
    "assessmentId": "a_7742",
    "subject": "math",
    "windowScore": 0.48,
    "trend": "down",
    "stateLabel": "fatigue_warning",
    "dataSufficient": true,
    "recordCount": 7
  },
  "recommendation": { "recommendationId": "rec_20301", "status": "pending" },
  "createdAt": "2026-08-16T19:46:00+08:00"
}
```

### 4.2 记录列表

| 项 | 内容 |
|---|---|
| URL | `/learning-records` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| subject | string(enum) | 否 | 按学科过滤 |
| dateFrom / dateTo | string(date) | 否 | 默认最近 30 天 |
| page / pageSize | integer | 否 | 分页 |

响应 `200`：`items`（结构同 4.1 响应的记录部分）+ `pagination`。

### 4.3 删除记录

| 项 | 内容 |
|---|---|
| URL | `/learning-records/{recordId}` |
| 方法 | `DELETE` |
| 说明 | 对应 PRD 5.2 边界场景「记录删除回溯」：删除后立即重算当前窗口，历史评估快照保留不改写 |

响应 `200`：

```json
{
  "deleted": true,
  "recordId": "r_88012",
  "recalculatedAssessment": {
    "assessmentId": "a_7751",
    "subject": "math",
    "windowScore": 0.53,
    "trend": "flat",
    "stateLabel": "insufficient_data",
    "dataSufficient": false,
    "recordCount": 2
  }
}
```

---

## 5. 状态评估 Assessments

> 状态分是记录的**派生资源**，不提供 POST 手动计算接口——提交/删除记录时自动重算，保证「分数始终由固定公式计算」（PRD 6.1），也避免前端伪造触发。

### 5.1 获取当前状态 ④

| 项 | 内容 |
|---|---|
| URL | `/assessments/current` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| subject | string(enum) | 否 | 不传返回全部学科的数组（PRD 5.2：不做跨学科加权综合） |

响应 `200`：

```json
{
  "items": [
    {
      "assessmentId": "a_7742",
      "subject": "math",
      "windowScore": 0.48,
      "trend": "down",
      "stateLabel": "fatigue_warning",
      "displayText": "最近几次数学状态有点走低，疲劳感比较明显",
      "dataSufficient": true,
      "recordCount": 7,
      "windowSize": 7,
      "basedOn": {
        "recordIds": ["r_88012", "r_87990", "r_87944"],
        "signals": ["自评疲劳度连续 3 次 ≥4", "练习正确率较上周下降"]
      },
      "computedAt": "2026-08-16T19:46:00+08:00"
    },
    {
      "assessmentId": null,
      "subject": "english",
      "stateLabel": "insufficient_data",
      "displayText": "数据积累中，再记录几次就能给出判断",
      "dataSufficient": false,
      "recordCount": 2,
      "windowSize": 7
    }
  ]
}
```

> `basedOn` 落实 PRD 8.3 可解释性——用户能看到「依据了哪些数据」，但不暴露权重与公式。冷启动时输出 `insufficient_data`，不下结论（PRD 5.2）。

### 5.2 状态历史（趋势曲线）

| 项 | 内容 |
|---|---|
| URL | `/assessments` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| subject | string(enum) | 是 | 历史按单学科查询 |
| dateFrom / dateTo | string(date) | 否 | 默认最近 30 天 |

响应 `200`：

```json
{
  "subject": "math",
  "items": [
    { "date": "2026-08-14", "windowScore": 0.61, "stateLabel": "efficient_stable", "trend": "flat" },
    { "date": "2026-08-15", "windowScore": 0.55, "stateLabel": "fluctuating_up", "trend": "down" },
    { "date": "2026-08-16", "windowScore": 0.48, "stateLabel": "fatigue_warning", "trend": "down" }
  ]
}
```

### 5.3 状态判断反馈

| 项 | 内容 |
|---|---|
| URL | `/assessments/{assessmentId}/feedback` |
| 方法 | `PUT` |
| 说明 | 「这个判断准不准」（PRD 第 9 节指标）；一条评估至多一份反馈，PUT 幂等可覆盖 |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| accurate | boolean | 是 | 判断是否准确 |

响应 `204`。

---

## 6. 个性化建议 Recommendations

对应 PRD 5.3。异步生成 + 模板兜底，任何情况下用户都拿得到内容。

### 6.1 手动请求生成建议

| 项 | 内容 |
|---|---|
| URL | `/recommendations` |
| 方法 | `POST` |
| 说明 | 常规路径由 4.1 自动创建，本接口仅用于手动刷新或阶段回顾；超频返回 `429` |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| scene | string(enum) | 是 | `post_session` / `weekly_review` |
| subject | string(enum) | 否 | `post_session` 场景建议必填 |
| recordId | string | 否 | `post_session` 场景关联的学习记录 |

响应 `202`：

```json
{
  "recommendationId": "rec_20301",
  "scene": "post_session",
  "subject": "math",
  "generation": { "status": "pending" },
  "createdAt": "2026-08-16T19:46:02+08:00"
}
```

### 6.2 获取建议 ⑤

| 项 | 内容 |
|---|---|
| URL | `/recommendations/{recommendationId}` |
| 方法 | `GET` |

响应 `200`（生成完成）：

```json
{
  "recommendationId": "rec_20301",
  "scene": "post_session",
  "subject": "math",
  "generation": { "status": "ready", "source": "llm", "completedAt": "2026-08-16T19:46:09+08:00" },
  "items": [
    {
      "title": "把单次时长压到 25 分钟",
      "content": "这次函数练了 45 分钟但中断了 3 次，后半程正确率明显掉下来了。下次试试练 25 分钟就停，中间歇 5 分钟。"
    },
    {
      "title": "先巩固再上新",
      "content": "今天难度感受偏难，暂时别急着推进新内容，明天先把函数图像的已掌握题型过一遍找回手感。"
    }
  ],
  "basedOn": {
    "assessmentId": "a_7742",
    "recordId": "r_88012",
    "stateLabel": "fatigue_warning",
    "explain": "依据最近 7 次数学记录的疲劳自评与正确率变化"
  },
  "feedback": null
}
```

> LLM 失败走兜底时 `generation.source` 为 `template`，其余结构完全一致，前端无需第二套渲染逻辑（对应 PRD 9 验收标准「API 全部不可用时核心流程不受影响」）。生成中时 `status` 为 `pending`，`items` 为 `null`。

### 6.3 建议列表

| 项 | 内容 |
|---|---|
| URL | `/recommendations` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| scene | string(enum) | 否 | 场景过滤 |
| subject | string(enum) | 否 | 学科过滤 |
| status | string | 否 | `ready`（默认）/ `all` |
| page / pageSize | integer | 否 | 分页 |

响应 `200`：`items`（结构同 6.2）+ `pagination`。

### 6.4 建议反馈

| 项 | 内容 |
|---|---|
| URL | `/recommendations/{recommendationId}/feedback` |
| 方法 | `PUT` |
| 说明 | 一条建议至多一份反馈，用户改主意即覆盖，PUT 幂等（PRD 6.5、第 9 节指标） |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| rating | string(enum) | 是 | `useful` / `neutral` / `not_useful` |
| reason | string | 否 | ≤100 字，补充为什么不准 |

响应 `200`：

```json
{
  "recommendationId": "rec_20301",
  "feedback": { "rating": "useful", "reason": null, "submittedAt": "2026-08-16T19:50:00+08:00" }
}
```

---

## 7. 学习总结与复盘 Summaries

对应 PRD 5.4。与建议同构（异步生成 + 反馈子资源），但不做模板兜底。周复盘由后台定时任务自动创建，无需客户端调用。

### 7.1 手动触发生成复盘

| 项 | 内容 |
|---|---|
| URL | `/summaries` |
| 方法 | `POST` |
| 说明 | 有每日次数上限，超限 `429`（PRD 5.4 控成本） |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| periodStart | string(date) | 是 | 起始日期 |
| periodEnd | string(date) | 是 | 结束日期，区间长度 3-31 天 |

响应 `202`：

```json
{
  "summaryId": "sum_4402",
  "periodStart": "2026-08-10",
  "periodEnd": "2026-08-16",
  "generation": { "status": "pending" },
  "createdAt": "2026-08-16T22:00:00+08:00"
}
```

### 7.2 获取复盘

| 项 | 内容 |
|---|---|
| URL | `/summaries/{summaryId}` |
| 方法 | `GET` |

响应 `200`（固定输出框架，PRD 5.4）：

```json
{
  "summaryId": "sum_4402",
  "periodStart": "2026-08-10",
  "periodEnd": "2026-08-16",
  "generation": { "status": "ready", "source": "llm", "completedAt": "2026-08-16T22:00:12+08:00" },
  "content": {
    "overview": "这周数学从「高效稳定」滑到了「疲劳预警」，主要发生在周四之后；英语记录太少，暂时看不出趋势。",
    "patterns": [
      "数学安排在 21 点后的 3 次记录，完成度都是部分完成，而下午的 2 次都完成了"
    ],
    "suggestions": [
      "把数学挪到下午或晚饭后早一点的时段试一周",
      "下周数学总时长先降到本周的 80%，稳住再加"
    ],
    "encouragement": "状态有起伏很正常，你这周把 7 次记录都填完了，这个坚持挺难得。"
  },
  "dataPoints": {
    "recordCount": 9,
    "subjects": ["math", "english"],
    "planCompletionRatio": 0.61,
    "referencedAssessmentIds": ["a_7742", "a_7710"]
  },
  "feedback": null
}
```

数据不足时（PRD 5.4 不硬凑）：

```json
{
  "summaryId": "sum_4403",
  "generation": { "status": "insufficient_data", "completedAt": "2026-08-16T22:00:03+08:00" },
  "content": null,
  "dataPoints": { "recordCount": 2, "minRequired": 5 },
  "message": "本周记录较少，暂不生成完整复盘"
}
```

### 7.3 复盘列表

| 项 | 内容 |
|---|---|
| URL | `/summaries` |
| 方法 | `GET` |

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page / pageSize | integer | 否 | 分页，按 `periodEnd` 倒序 |

响应 `200`：`items` + `pagination`。

### 7.4 复盘反馈

| 项 | 内容 |
|---|---|
| URL | `/summaries/{summaryId}/feedback` |
| 方法 | `PUT` |

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| rating | string(enum) | 是 | `useful` / `neutral` / `not_useful` |
| reason | string | 否 | ≤100 字 |

响应 `200`：结构同 6.4。

---

## 8. 接口清单速查

| # | 方法 | URL | 用途 | 流程环节 |
|---|---|---|---|---|
| 1 | GET | `/me` | 用户资料 | 前置 |
| 2 | PUT / PATCH | `/me` | 建档 / 更新资料 | 前置 |
| 3 | GET / PATCH | `/me/settings` | AI 调权 / 文本出域开关 | 前置 |
| 4 | POST / DELETE | `/me/guardian-authorization` | 监护人授权提交 / 撤销 | 合规 |
| 5 | GET | `/guardian-authorization/confirm` | 监护人确认 | 合规 |
| 6 | POST | `/goals` | **创建目标** | ① |
| 7 | GET | `/goals` | 目标列表与进度 | ① |
| 8 | PATCH | `/goals/{goalId}` | 修改 / 归档目标 | ① |
| 9 | POST | `/plans` | **生成计划** | ② |
| 10 | GET | `/plans` / `/plans/{planId}` | 计划列表 / 详情 | ② |
| 11 | PATCH | `/plans/{planId}/tasks/{taskId}` | 调整任务 / 确认完成 | ② |
| 12 | POST | `/learning-records` | **提交学习记录（同步回状态 + 建议句柄）** | ③④ |
| 13 | GET | `/learning-records` | 记录列表 | ③ |
| 14 | DELETE | `/learning-records/{recordId}` | 删除记录并重算 | ③ |
| 15 | GET | `/assessments/current` | **当前状态与标签** | ④ |
| 16 | GET | `/assessments` | 状态历史趋势 | ④ |
| 17 | PUT | `/assessments/{id}/feedback` | 「准不准」反馈 | ④ |
| 18 | POST | `/recommendations` | 手动请求建议 | ⑤ |
| 19 | GET | `/recommendations/{id}` | **获取建议内容** | ⑤ |
| 20 | GET | `/recommendations` | 建议列表 | ⑤ |
| 21 | PUT | `/recommendations/{id}/feedback` | 建议反馈 | ⑤ |
| 22 | POST | `/summaries` | 手动触发复盘 | 扩展 |
| 23 | GET | `/summaries` / `/summaries/{id}` | 复盘列表 / 详情 | 扩展 |
| 24 | PUT | `/summaries/{id}/feedback` | 复盘反馈 | 扩展 |

---

## 9. 端到端调用时序（完整闭环）

```
① POST /goals                                  → goalId=g_5501
② POST /plans        { planDate, availableMinutes:120, goalIds:[g_5501] }
                                               → planId=p_9001, tasks[...]
   (学习中) PATCH /plans/p_9001/tasks/t_30011  { status: "partial" }
③ POST /learning-records { planTaskId, behavior, selfReport }
④                                              ← 同步返回 assessment(stateLabel=fatigue_warning)
                                               ← 同步返回 recommendationId(pending)
⑤ GET  /recommendations/rec_20301              → 贴合本次情况的建议
   PUT  /recommendations/rec_20301/feedback    { rating: "useful" }

次日 ② POST /plans → adaptedFrom.stateLabel=fatigue_warning，任务量自动下调（闭环成立）
每周 后台自动 / POST /summaries → GET /summaries/{id} 拿到周复盘
```

---

## 10. 设计决策说明（两版取舍记录）

1. **状态计算不给独立 POST 接口**（两版一致）：状态分是确定性规则计算，提交/删除记录时触发重算，读取走 `GET /assessments/current`，读写分离，避免前端伪造触发。
2. **提交记录同步返回状态 + 顺带创建建议任务**（取 v2）：状态重算耗时可忽略，同步返回省一次往返；「学完想看建议」是必然路径，直接返回 pending 的 `recommendationId` 比让前端再 POST 一次更省事。v1 的异步重算方案在此场景下收益不明显。
3. **反馈统一用 PUT**（取 v2，并推广到状态反馈）：一个资源至多一份反馈，覆盖语义 + 幂等。状态反馈内容取 v1 的 `accurate` 布尔（PRD 第 9 节「这个判断准不准」）。
4. **保留监护人授权接口**（取 v1）：PRD 8.1/第 9 节将其列为可上线的最低要求，不能只在 403 层体现；接口收敛为提交/确认/撤销 3 个，不再展开。
5. **保留 PUT /me 幂等建档**（取 v1）：新用户 onboarding 需要一个全量建档语义，PATCH 只做局部更新。
6. **目标归档而非删除**（取 v2）：复盘和状态评估会引用历史目标，硬删造成引用悬空。
7. **枚举字典、统一分页结构、Idempotency-Key**（取 v2）：降低前后端沟通成本，覆盖弱网重复提交场景。
8. **建议兜底不改变响应结构**（取 v2）：`source` 区分 `llm` / `template`，`items` 结构一致，前端无需两套渲染。
9. **不做**：登录注册、家长端接口、权重配置读写接口（权重不对用户暴露，`UserWeightConfig` / `WeightAdjustLog` / `AICallLog` 均为内部实体不开放 API）、题库与具体题目内容。

## 11. 为后续板块预留（本版不实现）

| 预留点 | 做法 | 面向 |
|---|---|---|
| 学科维度贯穿 | `subject` 出现在记录/评估/建议/复盘所有资源上，状态永不跨学科合并 | 板块二接入学科知识库时无需改结构 |
| 生成留痕字段 | 所有 AI 产物带 `generation.source` + `basedOn` / `dataPoints` | PRD 6.5 可解释性、板块二画像溯源 |
| 复盘维度标记 | `summaries` 预留 `dimension` 字段（本版恒为 `state_and_plan`），板块二知识内容复盘用 `knowledge` | PRD 10.1 两类复盘边界 |
| 无跨用户读取接口 | 全部资源以当前 token 用户为作用域 | 板块三匿名聚合走独立统计视图层，不复用本 API |
| 供应商无关 | 响应中不出现任何模型厂商/模型名字段 | PRD 6.4 供应商抽象层 |

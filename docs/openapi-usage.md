# openapi.yaml 使用说明

> **当前口径（2026-09-19 实测）**：`docs/openapi.yaml` **v1.6.0 · 51 paths · 145 schemas**，是前后端与 QA 的**唯一契约真相源**（不是任何文档的"机器可读版本"）。
> 其早期母体 `api-design-unified.md` 已归档至 `docs/archive/`，不再维护；下文各「校验状态」章节是**各时点的历史校验记录**（数字为当时值，如 39 operation/71 schema），仅留痕，不代表当前文件。
> 变更规则：任何字段/实体/接口先改本文件（X0 评审），再写实现——见 `docs/refactor-module-contracts.md` §0。

## 三方怎么用

**前端 AI**：把 `openapi.yaml` 作为唯一接口契约喂给代码生成工具（如 `openapi-typescript`）或直接投喂给模型，据此生成 TypeScript 类型与请求函数，字段名、必填性、枚举取值一律以文件为准，不要凭猜测新增字段；重点关注 `RecordInput`（提交表单校验规则）、`StateResult`（含 `insufficient_data` 冷启动分支）和 `Recommendation`（`generation.status` 为 `pending` 时 `items` 为 `null`，需轮询）这三个 schema 的可空与分支处理。

**后端 AI**：以 `paths` 中的 `operationId` 为路由与 handler 命名依据、以 `components.schemas` 为请求校验与响应序列化的结构定义（`minimum`/`maximum`/`maxLength`/`enum` 直接落成校验规则），并遵守文件里已固化的三条服务端契约——提交与删除学习记录时同步重算状态快照、建议由 `POST /learning-records` 自动创建异步任务、LLM 失败时建议降级为 `template` 但响应结构不变。

**QA**：用 `npx @redocly/cli preview-docs docs/openapi.yaml` 或把文件拖进 [editor.swagger.io](https://editor.swagger.io) 打开 Swagger UI，在右上角 Authorize 填入 Bearer token 后按 ① 创建目标 → ② 生成计划 → ③ 提交记录 → ⑤ 获取建议的顺序逐个 Try it out（每个接口都带了可直接提交的请求示例），把上一步响应里的 `goalId` / `taskId` / `recommendationId` 填入下一步即可跑通完整闭环。

## 校验状态

已通过以下自动检查（脚本为临时文件，未入库）：

- YAML 语法合法，`openapi: 3.0.3`
- 220 处 `$ref` 全部可解析，无断链；64 个 schema 无未被引用的孤儿（注：此前写作「79 处 $ref」，79 是去重后的引用目标数，不是出现次数，已更正）
- 29 个 operation 均有 `summary`；POST/PUT/PATCH 均有 JSON request body（DELETE 语义上无请求体）；所有返回内容的响应均带示例
- 104 个属性名逐一比对源文档，无文档之外的字段
- 12 组枚举与源文档 0.4 节字典完全一致
- operation 清单与源文档第 8 节速查表逐条对应（速查表的 `{id}` 为排版简写，实际采用各章节定义的 `{recommendationId}` / `{summaryId}` / `{assessmentId}`）

## 2026-08-16 契约修订后的回归校验

本次修订（详见 `api-design-unified.md` 变更记录 v1.1）后重新验证：

- YAML 解析通过，20 个 path / 29 个 operation 结构不变
- 29 个 operation 均已声明 `500` 响应（引用 `components/responses/InternalServerError`）
- 16 个写操作全部声明 `Idempotency-Key`（`GET /guardian-authorization/confirm` 豁免：公开链接无鉴权）
- `AssessmentSnapshot.required` 收窄为 `[subject, stateLabel, dataSufficient, recordCount]`，`assessmentId` 可空——与 `StateResult` 语义一致
- `subjects` 的 `maxItems` 为 10，与 Subject 枚举取值数一致

## 2026-08-17 修复 500 插入导致的缩进错乱

v1.1 批量插入 500 时存在缩进 bug：成功响应（200/201/202/204）的 description/content/schema/example
被误缩进到 `'500'` 键之下，导致 29 个 operation 的成功响应全部失去 schema，且 500 因 `$ref`
带兄弟节点违反 OpenAPI 3.0 规范（兄弟节点会被忽略）。上表的「29 个 operation 均已声明 500」
当时是**形式通过但内容错误**——校验只检查了键存在，未检查内容归属。

本次修复后的验证（两层）：

1. 结构校验：YAML 解析通过；500 覆盖 29/29 且全部为**纯 `$ref`**（无兄弟节点）；29 个成功响应全部有 `content` 或 `description`。
2. 内容还原校验：与 500 插入前的版本（`4521861~1`）逐 operation 比对成功响应块，29 个中 28 个**逐字节一致**；唯一差异是 `DELETE /learning-records/{recordId}` 的示例，为 v1.1 有意修改（`insufficient_data` 时 `assessmentId: null`），其 schema 一致。

教训已吸收：后续对该文件的任何批量修改，验证必须断言**内容归属**（schema 挂在哪个状态码下），不能只断言键存在。

## 2026-08-17 鉴权对齐 + schema 约束补齐（v1.2）

- 收录 10 个 `/auth/*` 接口（operation 29→39），全局 security 从 `bearerAuth` 改为 `sessionCookie`（apiKey in cookie，名 `sid`）。8 个登录前接口标 `security: []`。
- 新增 7 个 auth schema（OkResponse / EmailOnlyRequest / RegisterRequest / LoginByCodeRequest / LoginByPasswordRequest / ResetPasswordRequest / AuthMeResponse）+ `EmailNotRegistered` 响应；schema 总数 64→71。
- schema 约束补齐：`windowScore` 三处加 0-1 范围、`LearningRecord.note` 回读字段、`Goal`/`GoalSummary` 增加可选 `outcome`+`completionNote`。
- 验证：YAML 解析通过；39 个 operation；所有 `$ref` 无断链（含新 auth schema 与 EmailNotRegistered）；8 个公开 auth 接口均 `security: []`。

## 2026-09-19 重构 M0 契约冻结（v1.6.0）

本次为重构第一阶段的**契约增量**：未改动任何既有字段名（增量式、向后兼容）。

- **稳定用户 ID 语义落地（D59）**：`User.userId` 描述明确为「稳定内部主键（`u_` 前缀），与登录凭证解耦，**不是邮箱**」；`AuthMeResponse.user` 增补可选 `userId`（`email` 仍 required，前端展示继续用它）。
- **新增 13 个实体 schema**：Exam / Collection / CollectionItem / UsageLedgerEntry / InviteCode / ViolationLog / ErrorReport / Medal / UserProfileEntry / TopicSummary / Explanation / ChatSession / ChatRawMessage；另加 5 个枚举：ErrorCause / ErrorIntent / ViolationAction / UserProfileGroup / ExplanationMode。
  ⚠️ 这些 schema **尚未挂到任何 path**——接口由各板块按里程碑补齐，字段名以本节为准（不得另起）。
- **题本升格（D48）**：`ErrorRecord` / `ErrorRecordCreate` / `ErrorRecordUpdate` 扩展 `errorCause` / `intent` / `sourceExamId`；`errorType` 保留为自由文本（历史兼容）。
- **目标（D6 / D49）**：`Goal` / `GoalSummary` / `GoalCreate` / `GoalUpdate` 增补 `parentGoalId`、`examId`、`targetScore`；**`status` 的 enum 未动**（`active`/`archived` 被 `?status=` 过滤依赖）。
- **游客态口径**写入 `info.description`：生产无有效会话一律 401（不再兜底共享账号），游客试用**不走后端接口**（不落库、不串号），A 板块落地时不得新增「游客可写」接口。
- **验证**：`yaml.safe_load` 解析通过；schema 总数 111 → **145**；paths 保持 **51**（本次不新增接口）；所有 `$ref` 可解析；对迁移后的空库跑 `alembic check` 报告 "No new upgrade operations detected"（迁移产物与 ORM 元数据完全一致）。
- 配套 DDL 见 `backend/alembic/versions/5015e9b1bdeb_m0_contracts_freeze_stable_user_id_new_.py`（单 head，`down_revision = 1a6f0c6bb285`）；空库 `upgrade head` 已在 SQLite 与 Neon Postgres 各验证一次，`downgrade` 亦验证可回退。
- **同轮定稿**（原则：X0 能定的不留悬念，让各板块直接开发）：
  - 新增 3 个 schema：`ChatContextStackItem`（上下文栈的栈项结构：branchType / intent / step / payload / enteredAt，并把三种 branchType 的**沉降去向**写进 description）、`UsageFeatureTier`（chat / embedded / advanced / multimodal）、`ReasoningTier`（quick / standard / deep）。
  - `ErrorCause` 补 `careless`（与既有自由文本口径对齐，共 6 值）。
  - `GoalCreate` / `GoalUpdate` 补 `pointIds`——**既有缺口**：`goals.point_ids` 列早已存在，但请求体一直没有该字段，建目标时根本传不进来。
  - `Exam` / `Collection` 补 `updatedAt`；`CollectionSnapshot` 补 `format`（markdown / plain，避免前端正则嗅探）；`UserProfileEntry` 补 `sourceRef`（画像 trace 线索）；`TopicSummary` 补 `sessionId`。
  - 三条口径写死进 description：对话原文留存窗口 **30 天**（取 §3.8.3 建议区间上限）、会话老化阈值 **7 天**（取 §3.8.1 建议区间偏长端）、**邀请码生成走后台脚本、不进用户产品 API**（口径同 D42）。
  - schema 总数 145 → **150**，paths 仍 51。

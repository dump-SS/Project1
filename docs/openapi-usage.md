# openapi.yaml 使用说明

`docs/openapi.yaml` 是 `docs/api-design-unified.md` 的机器可读版本，29 个 operation、64 个 schema，是前后端与 QA 的唯一契约来源。

## 三方怎么用

**前端 AI**：把 `openapi.yaml` 作为唯一接口契约喂给代码生成工具（如 `openapi-typescript`）或直接投喂给模型，据此生成 TypeScript 类型与请求函数，字段名、必填性、枚举取值一律以文件为准，不要凭猜测新增字段；重点关注 `RecordInput`（提交表单校验规则）、`StateResult`（含 `insufficient_data` 冷启动分支）和 `Recommendation`（`generation.status` 为 `pending` 时 `items` 为 `null`，需轮询）这三个 schema 的可空与分支处理。

**后端 AI**：以 `paths` 中的 `operationId` 为路由与 handler 命名依据、以 `components.schemas` 为请求校验与响应序列化的结构定义（`minimum`/`maximum`/`maxLength`/`enum` 直接落成校验规则），并遵守文件里已固化的三条服务端契约——提交与删除学习记录时同步重算状态快照、建议由 `POST /learning-records` 自动创建异步任务、LLM 失败时建议降级为 `template` 但响应结构不变。

**QA**：用 `npx @redocly/cli preview-docs docs/openapi.yaml` 或把文件拖进 [editor.swagger.io](https://editor.swagger.io) 打开 Swagger UI，在右上角 Authorize 填入 Bearer token 后按 ① 创建目标 → ② 生成计划 → ③ 提交记录 → ⑤ 获取建议的顺序逐个 Try it out（每个接口都带了可直接提交的请求示例），把上一步响应里的 `goalId` / `taskId` / `recommendationId` 填入下一步即可跑通完整闭环。

## 校验状态

已通过以下自动检查（脚本为临时文件，未入库）：

- YAML 语法合法，`openapi: 3.0.3`
- 79 处 `$ref` 全部可解析，无断链；64 个 schema 无未被引用的孤儿
- 29 个 operation 均有 `summary`；写操作均有 JSON request body；所有返回内容的响应均带示例
- 104 个属性名逐一比对源文档，无文档之外的字段
- 12 组枚举与源文档 0.4 节字典完全一致
- operation 清单与源文档第 8 节速查表逐条对应（速查表的 `{id}` 为排版简写，实际采用各章节定义的 `{recommendationId}` / `{summaryId}` / `{assessmentId}`）

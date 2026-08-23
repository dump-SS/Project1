# 板块二/三 下一步开发工作计划书

- 版本：v1.0
- 日期：2026-08-23
- 前置文档：`PRD-学习状态智能助手-v1.3.md`（实际内容 v1.4）、`docs/module2-3-gap-architecture-api-checklist.md`（差距清单，本计划书的输入）
- 覆盖范围：板块二「垂直学科落地」v2.1 → v2.3 全周期 + 板块三架构预留；板块一仅涉及必要的契约修复与衔接点改造
- 阅读对象：后端、前端、QA、内容运营、产品、法务

---

## 1. 背景与目标

### 1.1 背景

板块一 MVP（导学规划 / 状态量化 / 个性化建议 / 学习复盘）已交付。PRD v1.4 完成板块二详细设计（第 12 节），将产品从「通用学习管家」升级为「懂状态也懂内容」的双重引擎。代码现状（详见差距清单）：

- 板块二：前端 `/knowledge`、`/error-book` 演示页已上主导航（数据硬编码/localStorage）；后端仅 2 个无状态 LLM 文案接口；契约（openapi.yaml）零定义；无向量库、无 `kb_*` 表、无 mastery 引擎。
- 板块三：前端 `/community` 演示雏形已存在（localStorage 模拟）；后端与合规设计空白；PRD 定位仍为「规划中」。
- 存量隐患：现有 `/error-parse`、`/knowledge-summary` 接口违反 PRD 12.6 出域边界（P0 合规风险）；无 alembic 迁移机制；4 条板块一在用接口未入契约（契约漂移）。

### 1.2 总体目标

按 PRD 12.7 阶段化路径，用约 **3.5 个月**（含 2 周 P0 前置）完成板块二 MVP：

| 里程碑 | 目标 | 上线门（PRD 12.7） |
|---|---|---|
| P0 地基与合规（2 周） | 出域合规整改 + 契约先行 + 迁移机制 + 选型决策 | 无独立上线门，为 v2.1 解锁 |
| v2.1 最小可用（1.5 个月） | 数学单科：知识库只读 + 错题本手动录入 + mastery 基础计算 + PersonalData 内容掌握卡 | 错题录入→mastery 端到端跑通，1 个种子用户连续 2 周无回归 |
| v2.2 学科扩展（1 个月） | 物理/英语接入 + OCR 录入 + 间隔复习 + 知识复盘（dimension=knowledge） | 3 学科 mastery 端到端 + 种子用户周复盘连续 2 周可读 |
| v2.3 体验升级（1 个月） | 概念图谱可视化 + 错题自动归因（RAG）+ 薄弱路径高亮 + 隐私开关完善 | 5 个核心场景可演示；隐私工程评审通过 |

板块三本周期内**不做正式实现**，仅完成：演示页标注、统计视图层设计文档、授权位预留、隐私工程预评审。

### 1.3 成功衡量

- PRD 12.9 验收标准 6 项全部达成（见 §8 验收对照）；
- 合规底线：错题原文/作答/自述错因 100% 不出域（CI 断言）；监护人授权文案 v1.5 过法务评审；
- 工程底线：契约零漂移（openapi.yaml 为唯一真源）；核心流程在 LLM 全挂时可用。

---

## 2. 总体策略与工程原则

1. **契约先行**：任何接口动工前先改 `docs/openapi.yaml`，前后端与 QA 以此为唯一契约来源（沿用现有铁律）。契约评审通过后才允许写实现代码。
2. **合规前置**：P0 阶段先修出域漏洞再建新功能。所有板块二 LLM 调用必须经过 EgressGuard（data_class 白名单），不允许绕过。
3. **演示页转正，不推倒重写**：`Knowledge` / `ErrorBook` 页面交互已完成 70%，策略是「数据层换血」（localStorage/硬编码 → 真实 API），保留 UI。
4. **模型负责表达，规则负责事实**（PRD 6.1）：mastery 数值由固定公式计算，AI 只调权；所有 LLM 生成物过 6.3 审核层。
5. **降级永远可用**：embedding 挂 → 手动选知识点；LLM 挂 → 本地模板复盘；向量库挂 → 知识库浏览不受影响。
6. **增量兼容存量**：板块一表结构只增不改（`summaries.dimension`、`users` 设置项、v2.2 的 `goals.point_ids` 均为可空新列），不破坏现有调用方。

---

## 3. P0 阶段：地基与合规（第 1-2 周）

> 目标：拆除合规炸弹、立起契约与迁移地基、完成关键选型。本阶段不交付用户可见功能，但卡住后续一切。

### 3.1 任务分解

| # | 任务 | 负责方 | 产出物 | 估时 |
|---|---|---|---|---|
| P0-1 | **出域合规整改**：`/error-parse`、`/knowledge-summary` 加 `current_user` 鉴权 + `privacy_filter` 脱敏 + `safety_filter` 审核 + `AICallLog` 记录；前端两入口标注「演示」；`error-parse` 临时下线或改演示隔离（差距清单 §4 方案 A/B 评审定夺） | 后端 | 整改 PR + 合规说明 | 3d |
| P0-2 | **openapi.yaml 板块二契约**：17 条 API + 6 个 schema + 3 个 KB 错误码 + `Summary.dimension` + `UserSettings.knowledgeAiEgressEnabled`；同时修复 4 条契约漂移（`/daily-summary`、`/me/state-breakdown`、`/me/weight-config[/tune-now]`、`/recommendation-content`） | 后端主笔，前端/QA 评审 | openapi.yaml v1.5 | 3d（含评审） |
| P0-3 | **引入 alembic**：初始化迁移环境，将现有 `create_all` 基线化为首个 revision；写「新增表/列」迁移规范（CI 检查模型与迁移一致性） | 后端 | alembic 基线 + 规范文档 | 2d |
| P0-4 | **EgressGuard 落地**：`LLMProvider.generate()` 增加 `data_class` 参数；`knowledge_raw` 拒绝序列化 + audit log；板块一现有 3 处调用迁移为 `state_plan`；单测覆盖越权序列化场景 | 后端 | `egress_guard.py` + 改造 PR | 3d |
| P0-5 | **向量库与 embedding 选型决策**（PRD 12.11 待办）：FAISS / Chroma / Qdrant 三选一 POC（同 1000 条切片比召回质量与集成成本）；bge-small-zh-v1.5 / m3e-small 二选一（中文题干嵌入质量对比）；输出选型决策记录（ADR）。MVP 倾向：FAISS（零服务依赖）+ bge-small-zh | 后端 + 产品 | ADR 文档 + POC 报告 | 4d |
| P0-6 | **法务评审启动**：12.6 出域边界强化版 + 监护人授权文案 v1.5 + 错题录入敏感词策略 | 产品 + 法务 | 评审意见 | 并行，不阻塞开发 |
| P0-7 | **内容运营立项**：数学单科 50 知识点 + 关联关系预置清单模板确定（字段对齐 `kb_points` / `kb_point_relations` schema） | 产品 + 内容 | 内容清单模板 + 排期 | 并行 |

### 3.2 P0 完成定义（DoD）

- [ ] 两个违规接口整改完毕，安全组回归通过；
- [ ] openapi.yaml v1.5 评审通过并合入；
- [ ] alembic 基线合入，`upgrade head` 可从空库重建全部表；
- [ ] EgressGuard 单测覆盖率 100%（三类 data_class 各正反用例）；
- [ ] 选型 ADR 签字确认。

---

## 4. v2.1 阶段：最小可用（第 3-8 周，1.5 个月）

> 目标：数学单科端到端——学生能浏览知识库、录入错题、看到 mastery 出现在个人数据页。

### 4.1 后端任务

| # | 任务 | 关键设计点 | 估时 |
|---|---|---|---|
| 2.1-B1 | `kb_subjects` / `kb_points` / `kb_point_relations` 建模 + 迁移 | 按差距清单 §3.1 字段；`enabled` 过滤；`parent_id` 自关联 | 2d |
| 2.1-B2 | 数学 50 点种子数据导入脚本 | 内容团队交付 CSV/JSON → 幂等导入脚本（`scripts/`）；含版本号字段 | 2d（依赖 P0-7 内容交付） |
| 2.1-B3 | 知识库 5 个只读 API（`/knowledge/subjects`、`/points`、`/points/{id}`、`/graph` 占位、`/points/match`） | 全部 `current_user` 鉴权；`/graph` 在 v2.1 可先返 501 或仅返树；`/points/match` v2.1 用 embedding Top-5（向量库未就绪时降级为名称模糊匹配，接口形态不变） | 4d |
| 2.1-B4 | 本地 embedding 服务封装 | `embedding_service.py`：模型懒加载、`embed_mode=local/cloud/off` 开关、`KB_EMBEDDING_FAILED` 错误路径；模型打包方案（镜像 +50MB）随部署文档 | 3d |
| 2.1-B5 | FAISS 向量库封装 + `kb_embeddings` 表 | `vector_store.py`：按用户隔离 namespace；索引文件与 SQLite 同目录（PRD 12.2.3 可备份/销毁要求）；启动时懒加载/重建 | 3d |
| 2.1-B6 | `kb_errors` / `kb_error_points` 建模 + 错题本 5 个 API（CRUD，不含 review） | `raw_text` ≤4000 字（`KB_TEXT_TOO_LONG`）；软删（`deleted_at`，对齐 goals/archive）；录入前敏感词检测（复用 privacy_filter 模式，命中阻断或强制脱敏）；POST 后异步 embedding + 候选知识点匹配 | 5d |
| 2.1-B7 | mastery 引擎 `mastery_engine/` + `kb_point_mastery` 表 | 五因子公式（PRD 12.3.4），α₁..α₅ 入 `UserWeightConfig` 新增「内容维度」权重组（v2.1 用固定初始权重，调权链路 v2.2 再接）；触发式重算（错题保存后）；置信度规则：样本 <3 不返数值（`KB_INSUFFICIENT_MASTERY_DATA`） | 4d |
| 2.1-B8 | mastery 2 个 API（`/mastery/points/{id}`、`/mastery/subjects/{code}`） | 学科聚合权重 = 知识点占比（存 `kb_points.exam_weight`） | 2d |
| 2.1-B9 | 设置项 `knowledge_ai_egress_enabled`（GET/PATCH `/me/settings` 扩展） | 默认关闭（授权后开启），出域前 EgressGuard 检查该开关 | 1d |
| 2.1-B10 | CI 出域断言测试 | pytest + httpx 抓 provider 层入参：断言任何 `knowledge_raw` 字段不出现在出域 payload；覆盖错题全流程 | 2d |

后端小计：约 28 人日。

### 4.2 前端任务

| # | 任务 | 关键设计点 | 估时 |
|---|---|---|---|
| 2.1-F1 | `types/api.ts` 同步板块二 schema | 严格对应 openapi.yaml v1.5 | 1d |
| 2.1-F2 | `services/` 新增 `knowledge.ts`（扩）、`errorBook.ts`、`mastery.ts` | 走 `http.ts` 统一封装；沿用 localFallback 降级模式 | 2d |
| 2.1-F3 | Knowledge 页转正：`/knowledge/<subject>` 动态路由 + 真实数据 | 替换硬编码树；掌握度色点接 `/mastery/subjects/{code}`（无数据时按「数据积累中」展示）；「查看概念图谱」按钮 v2.1 保持占位 Modal | 3d |
| 2.1-F4 | ErrorBook 页转正：localStorage → `/error-book` API | 录入流程第四步「建议知识点」由 `utils/matchKnowledge.ts` 硬编码词表切换为 `GET /knowledge/points/match`；加录入前敏感词前端提示；列表/详情/编辑/软删接 API | 4d |
| 2.1-F5 | PersonalData 新增「内容掌握」MasteryCard | 新建组件插入 `pages/PersonalData/index.tsx` sections 数组（第 9 张卡）；复用 `SectionCard` 外壳与 `usePanelData` 模式；读 `/mastery/subjects/{code}` 按学科进度条展示 | 2d |
| 2.1-F6 | Settings 新增「知识复盘 AI 出域」开关 | `SWITCH_ITEMS` 数组加一项 + 隐私说明文案（等法务文案） | 0.5d |
| 2.1-F7 | mock-server 补板块二 mock（或决策停用 mock 直连后端） | 建议：v2.1 起业务后端已可用，前端 `.env.local` 直连 FastAPI，mock-server 仅保留 auth；写进 README | 1d |

前端小计：约 13.5 人日。

### 4.3 QA / 内容 / 合规任务

- QA：板块二 API 契约测试集（基于 openapi.yaml 生成）；错题全流程 E2E（录入→建议→确认→mastery 出现）；降级链路测试矩阵（embedding 挂 / LLM 挂 / 向量库挂）；
- 内容：数学 50 知识点 + 关联关系交付（第 4 周前），含定义、易错点、难度、考试权重；
- 合规：监护人授权文案 v1.5 定稿（第 6 周前，卡在 v2.1 上线门之前）。

### 4.4 v2.1 上线门验收

- [ ] 错题录入 → embedding → 知识点关联 → mastery 计算 → PersonalData 展示，端到端跑通；
- [ ] 1 个种子用户连续使用 2 周无回归；
- [ ] 出域 CI 断言全绿；
- [ ] 授权文案 v1.5 过法务评审并随功能上线。

---

## 5. v2.2 阶段：学科扩展（第 9-12 周，1 个月）

> 目标：三学科齐备 + 复习闭环 + 知识复盘上线。

### 5.1 任务分解

| # | 任务 | 负责方 | 估时 |
|---|---|---|---|
| 2.2-1 | 物理 100 点 + 英语 200 点内容交付与导入（复用 2.1-B2 脚本） | 内容 + 后端 | 内容 2 周（并行）/ 导入 1d |
| 2.2-2 | `summaries` 表 `dimension` 列迁移 + 板块一写入处补 `state_and_plan` | 后端 | 1d |
| 2.2-3 | 知识复盘改造：`POST /knowledge-summary` 重构为鉴权 + 结构化入参（periodStart/End/subject）+ 异步生成 + 落 summaries + RAG 检索（Top-K 片段仅本地）+ EgressGuard(`knowledge_aggregated`) + 审核层 + 频率限制（每日上限） | 后端 | 4d |
| 2.2-4 | `GET /knowledge-summary/{id}` 与列表接口；学科级自动周复盘定时任务（该学科 ≥3 条记录才触发） | 后端 | 2d |
| 2.2-5 | 艾宾浩斯复习：`kb_review_logs` + `POST /error-book/{id}/review` + 复习队列计算（间隔序列 1/2/4/7/15 天，recall_correct 驱动）+ 复习触发 mastery 重算 | 后端 | 3d |
| 2.2-6 | OCR 拍照录入（关键路径）：选型（云端 OCR API 需过 6.2 告知，或本地 PaddleOCR）→ 数学单科试点；图片不留存原文出域 | 后端 + 前端 | 5d（含选型） |
| 2.2-7 | mastery 调权链路接通：「内容维度」权重组纳入现有 `weight_tuning.py` 周期调权（沿用区间硬限制与留痕） | 后端 | 2d |
| 2.2-8 | `/mastery/subjects/{code}/timeline` API | 后端 | 1d |
| 2.2-9 | SummaryReview 页按 dimension 分 tab（状态与规划 / 知识内容）；`GET /knowledge-summary` 列表接入 | 前端 | 2d |
| 2.2-10 | ErrorBook 复习流程 UI：复习队列、复习时间线、recall 提交 | 前端 | 3d |
| 2.2-11 | OCR 录入交互：拍照/上传 → 识别 → 手动校正 → 走原录入流程 | 前端 | 3d |
| 2.2-12 | StudyGuide「建议先补」：plan 响应 recommendation 字段渲染短板提示（后端生成 plan 时查 mastery 排序） | 前后端各 | 1d + 1d |
| 2.2-13 | Recommendations 新增 `post_session_knowledge` 场景（内容维度建议） | 前后端各 | 1d + 1d |
| 2.2-14 | `Goal.point_ids`：目标绑定知识点（契约 + 迁移 + 目标表单加知识点选择器） | 前后端各 | 1d + 1d |
| 2.2-15 | `/knowledge/<subject>/summary` 页面（手动触发复盘 + 历史列表） | 前端 | 2d |

小计：后端约 18 人日，前端约 13 人日，内容 2 周（并行）。

### 5.2 v2.2 上线门验收

- [ ] 3 学科 mastery 端到端；
- [ ] 种子用户知识周复盘连续 2 周可读（人工评审生成质量）；
- [ ] OCR 数学单科识别可用率达标（试点数据说话，不达标则 OCR 降级为实验功能不影响上线）；
- [ ] 复盘生成内容过 6.3 审核层用例全绿。

---

## 6. v2.3 阶段：体验升级（第 13-16 周，1 个月）

| # | 任务 | 负责方 | 估时 |
|---|---|---|---|
| 2.3-1 | 图谱可视化选型：D3 vs vis-network POC（500 节点渲染性能 + 交互成本）→ ADR | 前端 | 2d |
| 2.3-2 | `GET /knowledge/subjects/{code}/graph` 正式实现（节点 + 4 类关系边） | 后端 | 2d |
| 2.3-3 | `/knowledge/<subject>/graph` 页面：力导向图、节点色阶 = mastery、点击联动详情 | 前端 | 4d |
| 2.3-4 | 错题自动归因（RAG 形态）：LLM 输入 = 检索片段 + 错因候选枚举（**不含原文**，替代现有 error-parse 的合规形态）；输出错因建议 + 置信度，用户确认后入库 | 后端 | 3d |
| 2.3-5 | 薄弱路径高亮：个人错题触达的知识点在图谱上叠加高亮（前端叠加层，数据来自 mastery + 错题关联） | 前端 | 2d |
| 2.3-6 | 隐私工程评审：出域链路全量走查、CI 断言补强、授权文案终稿 | 产品 + 法务 + 安全 | 评审周 |
| 2.3-7 | 性能达标：100 错题 + 1000 mastery P95 < 500ms 压测与调优（索引、异步重算、分页） | 后端 + QA | 3d |
| 2.3-8 | 5 个核心场景演示脚本与回归测试固化 | QA | 2d |

### v2.3 上线门验收（= 板块二 MVP 完整验收，PRD 12.9）

- [ ] 三学科错题本 + 知识库 + mastery 端到端；
- [ ] 错题原文/作答/自述错因 100% 不出域（CI 断言）；
- [ ] 知识复盘过 6.3 审核；
- [ ] 两类复盘入口在 `/summary-review` 清晰区分；
- [ ] 性能达标；
- [ ] LLM 全挂时核心流程（录入 / mastery 查看 / 本地模板复盘）可用。

---

## 7. 板块三：本周期仅做预留（不排开发期）

| # | 事项 | 产出 | 时间 |
|---|---|---|---|
| 3-A | `/community` 两页面标注「演示数据」水印/说明，避免用户误解 | 前端小改 | 随 v2.1 |
| 3-B | 统计视图层设计文档：独立于板块一/二原始表的匿名聚合视图设计（特征清单、聚合粒度、更新机制），不动代码 | 设计文档 | v2.2 期间 |
| 3-C | 隐私工程预评审：匿名化规则、最小群体规模（建议 k≥20）、反推风险评估 | 评审纪要 | v2.3 评审周同步 |
| 3-D | 契约预留：`/community/features`、`/community/aggregate`、`/me/community-consent` 三条接口写入 openapi.yaml 并标注 `x-status: planned` | 契约 | 随 v2.2 |

正式立项（真实上传与服务端聚合）待板块二 MVP 数据验证后单独立项。

---

## 8. 测试与质量保障计划

| 层 | 内容 | 工具/位置 |
|---|---|---|
| 契约测试 | 以 openapi.yaml 为源生成请求/响应校验；CI 阻断契约漂移 | schemathesis 或自研轻量校验 |
| 后端单测 | mastery 公式（含边界：样本<3、全极端值）、EgressGuard 三类 data_class 正反用例、复习间隔计算、软删过滤 | pytest（沿用 `backend/tests/`） |
| 出域断言（红线） | provider 层抓包断言：`rawText`/`studentAnswer`/`correctAnswer`/`errorNote`/检索片段原文/embedding 向量永不出现在出域 payload | CI 必跑，失败即阻断合并 |
| E2E | 错题全流程、知识复盘全流程、降级链路矩阵（embedding 挂/LLM 挂/向量库挂/网络断） | httpx + 前端 Playwright（可选） |
| 安全审核用例 | 6.3 禁止内容拦截用例（心理诊断、贬低表述、危机信号硬编码路径）在 knowledge 场景复测 | pytest |
| 性能 | 2.3-7 压测基线，纳入回归 | locust 或自研脚本 |
| 人工抽检 | 知识复盘生成内容每周抽样评审（沿用板块一机制） | 运营流程 |

---

## 9. 合规与隐私工作计划

| 事项 | 时间 | 负责 |
|---|---|---|
| P0-1 违规接口整改 | 第 1 周 | 后端 + 安全 |
| 出域边界 12.6 强化版法务评审 | 第 1-4 周 | 法务 |
| 监护人授权文案 v1.5（含板块二专款：错题原文不出本地说明） | 第 4-6 周定稿 | 法务 + 产品 |
| 错题录入敏感词检测策略评审 | 第 3 周 | 产品 + 法务 |
| OCR 数据出域告知（若选云端 OCR） | 第 9 周前 | 法务 |
| 板块二整体隐私工程评审 | 第 15 周 | 安全 + 法务 |

**红线**：法务评审未通过的项不随版本上线（功能可开关关闭，不阻塞其余功能）。

---

## 10. 风险登记册

| 风险 | 等级 | 影响 | 应对 |
|---|---|---|---|
| 现有 error-parse 出域漏洞被监管/用户发现 | 高 | 合规事故 | P0 第一周整改，不拖延 |
| 内容团队 50/100/200 知识点交付延期 | 高 | v2.1/v2.2 上线门 | 第 1 周锁定模板与排期；延期时 v2.1 可缩至 30 点保底 |
| 本地 embedding 模型体积与效果不达标 | 中 | 录入体验 | `embed_mode=cloud` 过渡开关（受 6.2 告知约束）；POC 阶段验证 |
| OCR 中英文/公式识别率参差 | 中 | v2.2 关键路径 | 仅数学单科试点；不达标则 OCR 转实验功能，手动录入保底 |
| mastery 公式校准缺乏真实数据 | 中 | 数值可信度 | v2.1 用保守初始权重 + 置信度规则兜底；种子用户数据回流后校准（同板块一调权方法论） |
| 图谱渲染性能（500+ 节点） | 低 | v2.3 体验 | 2.3-1 POC 先行；必要时按章节懒加载 |
| alembic 引入影响存量部署 | 中 | 板块一回归 | 基线 revision 与现有 `create_all` 产物做 schema diff 校验 |
| 板块三演示页被误认为真实群体数据 | 中 | 信任风险 | 3-A 标注随 v2.1 上线 |

---

## 11. 排期总表

```
周次      1-2        3-4        5-6        7-8        9-10       11-12      13-14      15-16
        ┌────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
后端    │ P0 整改 │ kb建模+  │ 错题API+ │ mastery+ │ 复盘重构 │ OCR+复习 │ graph API│ 自动归因 │
        │ 契约   │ 知识库API│ 向量库   │ 联调收尾 │ +迁移    │ 调权接通 │ +压测    │ +评审    │
        │ alembic│          │          │          │          │          │          │          │
        ├────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
前端    │ 契约   │ types/   │ Knowledge│ Mastery卡│ summary  │ 复习UI   │ 图谱POC  │ 图谱页+  │
        │ 评审   │ services │ 转正     │ +设置开关│ 分tab    │ +OCR交互 │          │ 薄弱路径 │
        ├────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
内容    │ 模板   │ 数学50点 │ 数学50点 │ 交付     │ 物理100  │ 英语200  │ 复盘抽检 │ 复盘抽检 │
        ├────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
合规    │ 整改   │ 法务评审 │          │ 文案定稿 │ OCR告知  │          │          │ 隐私评审 │
        ├────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
门      │        │          │          │ ▲v2.1    │          │ ▲v2.2    │          │ ▲v2.3    │
        └────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

人力估算：后端约 60 人日，前端约 35 人日，QA 约 15 人日，内容运营约 4 周，合规/法务穿插。按 1 后端 + 1 前端 + 0.5 QA 配置，周期约 16 周（含 buffer）。

---

## 12. 角色分工建议

| 角色 | 职责 |
|---|---|
| 后端（1 人） | 契约、建模/迁移、EgressGuard、向量库/embedding、错题/mastery/复盘引擎、性能 |
| 前端（1 人） | types/services、两演示页转正、MasteryCard、复习与 OCR 交互、图谱页 |
| QA（0.5 人） | 契约测试、出域断言 CI、E2E、降级矩阵、压测 |
| 产品 | 内容模板与排期、法务对接、种子用户运营、复盘抽检 |
| 内容运营（外协） | 三学科知识点与关联关系清单 |
| 法务/安全（评审） | 出域边界、授权文案、隐私工程评审 |

---

## 13. 立即行动项（本周）

1. 召开 P0 启动会：确认差距清单 §4 整改方案选型（A/B/C）、确认本计划书排期；
2. 后端启动 P0-1（违规接口整改）与 P0-4（EgressGuard）；
3. 产品发出法务评审请求（出域边界强化版 + 授权文案 v1.5）；
4. 产品锁定内容运营：数学 50 点清单模板与交付排期；
5. 后端启动 P0-5 选型 POC（向量库 + embedding）。

---

## 附：文档关系

- 差距与接口细节：`docs/module2-3-gap-architecture-api-checklist.md`
- 需求依据：`PRD-学习状态智能助手-v1.3.md` 第 12 节、10.2、6.2/6.3
- 契约真源：`docs/openapi.yaml`（P0-2 后升级为 v1.5）
- 本计划书评审通过后，P0 任务拆入迭代看板执行。

# 模块二 / 模块三 未完成内容、架构及接口对齐设计清单

- 版本：v1.0
- 日期：2026-08-23
- 依据：`PRD-学习状态智能助手-v1.3.md`（实际内容为 PRD v1.4，含第 12 节板块二详细设计）、`docs/openapi.yaml`、`README.md`、backend / frontend / mock-server 代码现状盘点
- 范围：板块二「垂直学科落地」（PRD 第 12 节）+ 板块三「群体匿名参照」（PRD 10.2）
- 阅读对象：后端、前端、QA、内容运营

---

## 0. 现状结论（TL;DR）

| 层 | 板块二现状 | 板块三现状 |
|---|---|---|
| 契约（openapi.yaml） | ❌ 零定义（30 条路径全部属于板块一） | ❌ 零定义 |
| 后端（FastAPI） | ⚠️ 仅 2 个无状态 LLM 文案接口（`POST /knowledge-summary`、`POST /error-parse`），不落库、不鉴权、不过审核层，**且违反出域边界（见 §4，P0）** | ❌ 完全空白 |
| 前端（Vite/React） | ⚠️ `/knowledge`、`/error-book` 演示页已上导航，数据硬编码 / localStorage | ⚠️ `/community/upload`、`/community/compare` 演示页已存在，纯 localStorage 模拟 |
| mock-server | ❌ 无板块二接口 | ❌ 无板块三接口 |

**总体判断**：板块二处于「演示壳已搭、契约与后端为零」阶段；板块三处于「前端演示雏形已存在、后端与合规设计为零」阶段。动工顺序应为：**先补契约 → 再改 LLM 出域管控（P0 合规）→ 再建数据模型 → 最后前后端联调**。

---

## 1. 板块二未完成内容清单

### 1.1 学科知识库（PRD 12.3.1）

| 项目 | 状态 | 现状位置 | 缺口 |
|---|---|---|---|
| `kb_subjects` / `kb_points` / `kb_point_relations` 表 | ❌ | — | backend 无任何 `kb_` 前缀模型，需从零建模 |
| 知识库内容预置（数学 50 点，v2.1） | ❌ | — | 无数据导入机制（需种子数据脚本 + 内容团队清单） |
| `GET /knowledge/subjects` 等 5 个只读 API | ❌ | — | 契约与后端均无 |
| `/knowledge/<subject>` 动态路由 | ⚠️ | `frontend/src/pages/Knowledge/index.tsx` | 仅写死「数学」单学科、硬编码 7 个节点，无路由参数 |
| 树 + 图双视图 | ⚠️ | 同上 | 树视图已有（antd Tree）；图视图未做，「查看概念图谱」按钮只弹占位 Modal |
| 节点 hover 掌握度色阶（红<40/橙40-70/绿>70） | ⚠️ | 同上 | 色点+百分比已常显，但数值是硬编码，未接 `/mastery` 数据 |
| 知识点详情页（定义/易错点/关联题/关联概念） | ⚠️ | 同上 | 右侧详情面板已有结构，但无真实数据、未打通错题本与图谱 |

### 1.2 错题本（PRD 12.3.2）

| 项目 | 状态 | 现状位置 | 缺口 |
|---|---|---|---|
| `kb_errors` / `kb_error_points` / `kb_review_logs` 表 | ❌ | — | 需从零建模 |
| `GET/POST/PATCH/DELETE /error-book` + `POST /error-book/{id}/review` | ❌ | — | 契约与后端均无 |
| 录入流程（选学科→粘贴→建议知识点→确认→选错因） | ⚠️ | `frontend/src/pages/ErrorBook/index.tsx` | 流程 UI 完整，但：①知识点建议用 6 条硬编码词表（`utils/matchKnowledge.ts`）而非向量检索 Top-5；②数据落 localStorage（`errors_{subject}`）而非后端；③无敏感词检测（PRD 12.10 要求录入前脱敏/阻断） |
| 错题原文 embedding + `vectorId` 回写 | ❌ | — | 无向量库、无 embedding 依赖 |
| 复习流程（间隔复习 / 艾宾浩斯，v2.2） | ❌ | — | 无复习队列、无 `kb_review_logs`、无复习时间线 UI |
| 拍照 OCR 录入（v2.2） | ❌ | — | 无 OCR 依赖与交互 |
| 自动归因（LLM 看检索片段，v2.3） | ⚠️ | `backend/routes/knowledge.py:140` `POST /error-parse` | 已有 LLM 解析接口，但**直接把错题原文/作答/答案发给云端 LLM，违反 PRD 12.6**（见 §4）；且未走 RAG 检索、未过 6.3 审核层 |

### 1.3 概念关联图谱（PRD 12.3.3，v2.3）

| 项目 | 状态 | 缺口 |
|---|---|---|
| 4 类关系（prerequisite / derived / contrast / applied_in）建模 | ❌ | `kb_point_relations` 表未建 |
| `GET /knowledge/subjects/{code}/graph` | ❌ | 契约与后端均无 |
| `/knowledge/<subject>/graph` 页面（D3/vis-network） | ❌ | 无页面；`frontend/package.json` 无 d3 / vis-network / echarts 依赖（仅 recharts），需先选型 |
| 错题触达后「薄弱路径」高亮 | ❌ | 依赖 mastery + 图谱，v2.3 |

### 1.4 知识点掌握画像（PRD 12.3.4）

| 项目 | 状态 | 缺口 |
|---|---|---|
| `kb_point_mastery` 表（user_id × point_id） | ❌ | 需从零建模 |
| mastery 五因子公式（错题率/练习正确率/复习新近度/间隔保持/未解决扣分） | ❌ | 规则引擎未写；注意需与 `backend/state_engine/` 风格保持一致 |
| α₁..α₅ 纳入板块一同一调权机制（新增「内容维度」权重组） | ❌ | `backend/state_engine/weight_tuning.py` 目前只有状态权重组，需扩展 |
| `GET /mastery/points/{id}`、`/mastery/subjects/{code}`、`/mastery/subjects/{code}/timeline` | ❌ | 契约与后端均无 |
| 置信度规则（样本 <3 不出数值，报 `KB_INSUFFICIENT_MASTERY_DATA`） | ❌ | — |
| 前端 3 个嵌入点（知识库 hover / PersonalData 内容掌握卡 / study-guide 建议先补） | ❌ | 见 §5 衔接点清单 |

### 1.5 知识复盘（PRD 12.3.5）

| 项目 | 状态 | 现状位置 | 缺口 |
|---|---|---|---|
| `summaries` 表 `dimension` 字段 | ❌ | `backend/models/summary.py` | 无该列，需迁移新增（`state_and_plan` / `knowledge` 两取值） |
| `POST /knowledge-summary` 落库 + 异步生成 | ⚠️ | `backend/routes/knowledge.py:63` | 现为「入参字符串→出参文案」无状态接口：不鉴权（未加 `current_user`）、不落库、无 periodStart/End 结构化入参、无 RAG、无审核层、无频率限制 |
| 学科级自动周复盘（该学科 ≥3 条记录才触发） | ❌ | — | 无定时任务机制 |
| `/knowledge/<subject>/summary` 前端页 + `/summary-review` 按 dimension 分 tab | ❌ | `frontend/src/pages/SummaryReview/index.tsx` | 现仅板块一复盘，无 tab 分组 |
| 纯本地规则化模板降级（设置开关关闭云端时） | ❌ | — | 现降级文案是固定死的一段话，非「基于本地数据的模板生成」 |

### 1.6 隐私与出域管控（PRD 12.6）

| 项目 | 状态 | 缺口 |
|---|---|---|
| `LLMProvider` 增加 `data_class` 标签（state_plan / knowledge_aggregated / knowledge_raw） | ❌ | `backend/llm_provider.py` 无此概念 |
| provider 层拒绝序列化 `knowledge_raw` + audit log | ❌ | — |
| 出域 payload pydantic 白名单过滤 | ❌ | 现仅有 `privacy_filter.py` 正则脱敏（手机/身份证/邮箱/QQ），无字段级白名单 |
| 设置页「知识复盘 AI 出域」开关 | ❌ | `backend/models/user.py:50-51` 仅 2 个开关；前端 `Settings` 的 `SWITCH_ITEMS` 数组加一项即可 |
| 监护人授权文案板块二专款（v1.5 改版） | ❌ | — |
| 错题录入敏感词检测 | ❌ | — |

### 1.7 基础设施

| 项目 | 状态 | 缺口 |
|---|---|---|
| 本地向量库（FAISS / Chroma / Qdrant） | ❌ | `backend/pyproject.toml` 无任何向量/embedding 依赖，PRD 12.11 选型未定 |
| 本地 embedding 模型（bge-small-zh / m3e-small） | ❌ | 含打包方案（镜像 +50MB 问题）与 `embed_mode=cloud` 过渡开关 |
| `kb_embeddings` 表 | ❌ | — |
| 数据库迁移（alembic） | ❌ | 现为 `create_all`（`backend/main.py:32`），新增 `kb_*` 表 + `summaries.dimension` 列前必须先引入迁移机制 |
| KB 系列错误码 | ❌ | `KB_TEXT_TOO_LONG` / `KB_EMBEDDING_FAILED` / `KB_INSUFFICIENT_MASTERY_DATA` 均未定义 |

---

## 2. 板块三未完成内容清单

PRD 对板块三仅作方向性规划（10.2），但前端已存在演示雏形，需明确「演示版」与「合规版」的差距：

| 项目 | 状态 | 现状位置 | 缺口 |
|---|---|---|---|
| 匿名特征值上传 API | ❌ | `frontend/src/pages/Community/Upload.tsx` | 现为纯 localStorage 模拟（`community_my_data` / `community_pool`），无后端、无真实多用户数据 |
| 匿名化/脱敏规则设计 | ❌ | — | 需专门隐私工程评审（PRD 10.2 明确是上线前置条件）：特征值清单、k-匿名最小群体规模、禁止上传字段黑名单 |
| 最小群体规模限制（防小样本反推个体） | ❌ | `Compare.tsx` 同学科对比仅在样本 >1 时展示 | 演示版阈值=1，合规版需定义最小 N（如 ≥20）并在后端强制 |
| 统计视图层（独立于板块一原始数据的匿名聚合视图） | ❌ | — | PRD 10.3 架构预留项，需在数据层设计独立统计视图，避免改动板块一原始表 |
| 用户显式授权动作（匿名聚合必须是显式、可感知的授权） | ❌ | — | 现演示版无授权流程；需授权开关 + 可撤回机制 |
| 群体对比 API（百分位/分布数据由服务端计算下发） | ❌ | `Compare.tsx` 全部前端本地计算 | 真实版应由服务端只下发聚合统计（分位数、直方图桶），不下发他人个体特征 |

**定位建议**：板块三在 PRD 中仍是「规划中」，当前演示页建议保留但标注「演示数据」；正式立项前只做架构预留（统计视图层 + 授权位），不做真实上传。

---

## 3. 架构对齐设计

### 3.1 数据模型增量（对齐 PRD 12.4）

新增 8 张表（全部 `kb_` 前缀，与板块一共享 `data.db`）：

| 表 | ORM class | 关键字段 | 备注 |
|---|---|---|---|
| `kb_subjects` | `KnowledgeSubject` | id, code, name, grade_band, version, enabled | `enabled=true` 才可查 |
| `kb_points` | `KnowledgePoint` | id(`kp_`), subject_code, code, name, definition, parent_id, difficulty, exam_weight | parent_id 构树 |
| `kb_point_relations` | `KnowledgePointRelation` | id(`kpr_`), src_id, dst_id, type, weight | type ∈ 4 种关系枚举 |
| `kb_errors` | `ErrorRecord` | id(`err_`), user_id, subject, raw_text, student_answer, correct_answer, error_type, error_note, vector_id, status, created_at, last_reviewed_at, deleted_at | raw_text ≤4000 字；软删对齐 goals/archive 风格 |
| `kb_error_points` | `ErrorPoint` | error_id, point_id, confidence | 多对多 + 置信度 |
| `kb_point_mastery` | `PointMastery` | user_id, point_id, mastery, sample_size, updated_at | 联合唯一索引 (user_id, point_id) |
| `kb_review_logs` | `ReviewLog` | id(`rvl_`), error_id, reviewed_at, recall_correct, interval_days | 艾宾浩斯间隔由它驱动 |
| `kb_embeddings` | `EmbeddingRef` | vector_id, ref_type('error'/'point'), ref_id, model, dim, created_at | 向量本体存本地向量库，表只存引用 |

板块一存量表改动（仅 2 处，纯增量）：
1. `summaries` 表新增 `dimension` 列（`state_and_plan` 默认 / `knowledge`）——**需 alembic 迁移**；
2. `users` 设置新增 `knowledge_ai_egress_enabled`（默认开启与否需产品定，建议默认关、授权后开）；
3. v2.2 起 `goals` 增 `point_ids` 可选字段（PRD 12.8）。

**前置工作**：引入 alembic。当前 `create_all` 无法给存量表加列，板块二是引入迁移机制的最后窗口期。

### 3.2 LLM 出域管控改造（对齐 PRD 12.6，最高优先级）

现状 `backend/llm_provider.py` 的 `generate(prompt, context)` 对出域零管控。改造方案：

```
LLMProvider.generate(prompt, context, data_class: DataClass)

DataClass = "state_plan" | "knowledge_aggregated" | "knowledge_raw"

调用链：
业务层（显式声明 data_class + pydantic payload 模型）
  → EgressGuard（白名单校验）：
      - state_plan：沿用板块一规则（结构化特征 + 用户文本，受 send_text_to_ai 开关约束）
      - knowledge_aggregated：仅放行白名单字段（错因枚举、mastery 数值、检索片段元信息、状态摘要）
      - knowledge_raw：直接拒绝序列化，audit log 记 ERROR，抛 EgressViolation
  → privacy_filter（正则脱敏，沿用）
  → safety_filter（6.3 审核层，生成物回检）
  → provider（供应商抽象，沿用）
```

配套：
- `AICallLog` 增加 `data_class` 与 `egress_blocked` 字段，支撑审计与成本监控（6.4/6.5）；
- 每个板块二接口定义独立的 pydantic「出域 payload 模型」，与「入库模型」分离，从类型层面杜绝 rawText 混进出域包。

### 3.3 本地 RAG 链路（对齐 PRD 12.2.3）

```
错题录入 → 本地 embedding（bge-small-zh / m3e-small，二选一待 12.11 决策）
        → 向量入本地向量库（FAISS / Chroma / Qdrant，三选一待决策；MVP 建议 FAISS，零服务依赖）
        → kb_embeddings 存引用
知识点建议 → rawText 向量 vs kb_points 向量 cosine Top-5 + 匹配打分 → 用户确认
知识复盘 → 检索 Top-K 片段（仅本地）+ 聚合画像 → EgressGuard(knowledge_aggregated) → 云端 LLM → 审核层 → 落 summaries
```

降级路径：云端 LLM 不可用 → 本地规则化模板（方案 C）；embedding 不可用 → 报 `KB_EMBEDDING_FAILED`，录入降级为手动选知识点（不阻断）。

### 3.4 mastery 计算与调权衔接（对齐 PRD 12.3.4 / 12.10）

- mastery 五因子公式放 `backend/state_engine/` 同级新模块（如 `mastery_engine/`），与状态引擎同风格：公式固定、权重入库；
- α₁..α₅ 作为「内容维度」权重组挂入现有 `UserWeightConfig` 体系，`weight_tuning.py` 扩展支持多权重组；
- 重算触发：错题保存后、复习提交后（触发式）+ 每日批量（兜底）；
- 板块一 5.2 只读消费 mastery 数值（`knowledge_aggregated`，允许出域），不反向依赖。

---

## 4. 关键合规风险（P0，动工前必须处理）

**现有 `backend/routes/knowledge.py` 两个接口违反 PRD 12.6 出域边界：**

| 接口 | 问题 |
|---|---|
| `POST /error-parse` | 把 `question_text` / `student_answer` / `correct_answer`（错题原文，属 `knowledge_raw`）**直接拼进 prompt 发给云端 LLM**，PRD 12.6 明确禁止出域 |
| `POST /knowledge-summary` | 入参 `error_summary` 由前端自由拼字符串，无白名单校验，无法保证不含错题原文 |

其他问题：两接口均未加 `current_user` 鉴权、未过 6.3 安全审核层、未写 `AICallLog`、降级文案为固定话术（含「函数单调性」等具体内容，对其他学科用户是误导）。

**处置建议（三选一，建议 A）：**
- A. 立即下线/鉴权化这两个接口，按 §3.2 改造后重新上线；
- B. 保留为「演示专用」但加 `X-Demo` 隔离 + 不接入真实供应商 key；
- C. 短期至少补：鉴权 + `privacy_filter` 脱敏 + 审核层 + 前端标注「演示」。

同时注意：板块二验收标准要求「错题原文 100% 不出域（CI 端到端测试断言）」，需补对应测试用例。

---

## 5. 接口对齐设计清单（openapi.yaml 待新增）

### 5.1 板块二 API（对齐 PRD 12.5，共 17 条）

**知识库只读（5）**

| 方法 | 路径 | 说明 | 优先级 |
|---|---|---|---|
| GET | `/knowledge/subjects` | 已启用学科列表（含知识点数、版本） | v2.1 |
| GET | `/knowledge/subjects/{code}/points` | 学科知识点树 | v2.1 |
| GET | `/knowledge/points/{pointId}` | 单点详情（定义/关联关系） | v2.1 |
| GET | `/knowledge/subjects/{code}/graph` | 节点+边全图 | v2.3 |
| GET | `/knowledge/points/match?text=` | 文本→候选知识点 Top-K | v2.1 |

**错题本（6）**

| 方法 | 路径 | 说明 | 优先级 |
|---|---|---|---|
| GET | `/error-book?subject=&status=&page=` | 列表 | v2.1 |
| POST | `/error-book` | 录入（异步 embedding+匹配） | v2.1 |
| GET | `/error-book/{errorId}` | 详情 | v2.1 |
| PATCH | `/error-book/{errorId}` | 改错因/状态/关联点 | v2.1 |
| DELETE | `/error-book/{errorId}` | 软删 | v2.1 |
| POST | `/error-book/{errorId}/review` | 复习（recall_correct → 更新 review log + 触发 mastery 重算） | v2.2 |

**掌握画像（3）**

| 方法 | 路径 | 说明 | 优先级 |
|---|---|---|---|
| GET | `/mastery/points/{pointId}` | 单点 mastery+置信度+样本量 | v2.1 |
| GET | `/mastery/subjects/{code}` | 学科聚合+子项贡献 | v2.1 |
| GET | `/mastery/subjects/{code}/timeline?from=&to=` | 时间序列 | v2.2 |

**知识复盘（3，改造现有 2 条 + 新增 1 条）**

| 方法 | 路径 | 说明 | 优先级 |
|---|---|---|---|
| POST | `/knowledge-summary` | **改造**：加鉴权、结构化入参（periodStart/End/subject 必填）、异步落 summaries、走 RAG+EgressGuard+审核层、频率限制 | v2.2 |
| GET | `/knowledge-summary/{summaryId}` | 详情（复用 summaries 表，`dimension=knowledge`） | v2.2 |
| GET | `/knowledge-summary?subject=&from=&to=` | 列表（summary-review 双 tab 数据源） | v2.2 |

**`/error-parse` 处置**：不进契约或标记 deprecated，按 §4 整改后再议（v2.3 自动归因的正确形态是「LLM 看检索片段+错因候选」，不是看原文）。

### 5.2 schema 与字段新增

- `KnowledgeSubject` / `KnowledgePoint` / `KnowledgePointRelation` / `ErrorRecord` / `PointMastery` / `KnowledgeSummary` 等 schema，同步进 `frontend/src/types/api.ts`；
- `Summary` schema 增 `dimension: "state_and_plan" | "knowledge"`；
- `UserSettings` 增 `knowledgeAiEgressEnabled: boolean`；
- v2.2：`Goal` 增 `pointIds: string[]`（可选）；
- 错误码新增：`KB_TEXT_TOO_LONG`、`KB_EMBEDDING_FAILED`、`KB_INSUFFICIENT_MASTERY_DATA`，沿用 `{ error: { code, message, field? } }` 统一格式。

### 5.3 契约漂移修复（板块一遗留，随本次一并补）

前端在用但契约未定义的 4 条，需补入 openapi.yaml 或改造下线：
`GET /daily-summary`、`GET /me/state-breakdown`、`GET /me/weight-config` + `POST /me/weight-config/tune-now`、`GET /recommendation-content`。

### 5.4 板块三接口（仅预留，不实施）

| 方法 | 路径（建议） | 说明 |
|---|---|---|
| POST | `/community/features` | 匿名特征值上传（显式授权后） |
| GET | `/community/aggregate?subject=&metric=` | 聚合统计下发（百分位/直方图桶，含最小群体规模校验） |
| GET/PUT | `/me/community-consent` | 匿名聚合授权状态与开关 |

---

## 6. 前后端衔接点改造清单（对齐 PRD 12.8）

| # | 入口 | 改造内容 | 前端改动点 | 后端依赖 | 阶段 |
|---|---|---|---|---|---|
| 1 | `/personal-data` | 新增「内容掌握」SectionCard | 新建 `MasteryCard` 组件插入 `pages/PersonalData/index.tsx` 的 sections 数组（外壳 `SectionCard` 现成，声明式扩展） | `GET /mastery/subjects/{code}` | v2.1 |
| 2 | `/study-guide` | 推荐补「建议先补：xxx（掌握 55%）」 | 生成 plan 响应的 recommendation 字段渲染短板提示 | 后端生成 plan 时查 mastery 按短板排序 | v2.2 |
| 3 | `/recommendations` | 新增「内容维度」建议场景 | RecScene 枚举 + 列表分组 | `recommendations.scene` 增 `post_session_knowledge` | v2.2 |
| 4 | `/summary-review` | 两类摘要按 dimension 分 tab | `SummaryReview/index.tsx` 加 tab（状态与规划 / 知识内容） | summaries.dimension + 列表接口 | v2.2 |
| 5 | `/goals` | 学科目标绑定知识点 | 目标表单加知识点选择器 | `Goal.point_ids` | v2.2 |
| 6 | `/settings` | 「知识复盘 AI 出域」开关 | `Settings/index.jsx` 的 `SWITCH_ITEMS` 数组加一项 + 隐私说明文案 | `UserSettings.knowledgeAiEgressEnabled` | v2.1 |

另：板块二前端两个演示页转正清单——
- `Knowledge/index.tsx`：接 `/knowledge/subjects/{code}/points` 真实数据、加 `<subject>` 路由参数、掌握度接 `/mastery`、图视图等 v2.3 选型后补；
- `ErrorBook/index.tsx`：localStorage → `/error-book` API；`utils/matchKnowledge.ts` 硬编码词表 → `GET /knowledge/points/match`；录入前加敏感词检测；
- mock-server 需补板块二 17 条 mock（或前端继续 localFallback 过渡，二选一并写进 README）。

---

## 7. 实施优先级与排期建议（对齐 PRD 12.7）

| 批次 | 内容 | 对应阶段 |
|---|---|---|
| **P0（先行，1-2 周）** | §4 合规整改（error-parse / knowledge-summary）；openapi.yaml 板块二契约 + §5.3 漂移修复；引入 alembic；向量库与 embedding 选型决策（PRD 12.11 待办） | v2.1 前置 |
| **P1（v2.1，1.5 个月）** | kb_subjects/points/relations 建模 + 数学 50 点种子数据；知识库 5 个只读 API + Knowledge 页转正；错题本 CRUD + ErrorBook 页转正；mastery 基础计算 + 2 个 API + PersonalData 内容掌握卡；EgressGuard + data_class 改造；设置开关；CI 出域断言 | v2.1 上线门：错题录入→mastery 端到端 |
| **P2（v2.2，1 个月）** | 物理/英语学科接入；OCR 录入；艾宾浩斯复习（review API + 复习 UI）；summaries.dimension + 知识复盘异步生成 + summary-review 分 tab；study-guide 短板提示；Goal.point_ids | v2.2 上线门：3 学科端到端 + 周复盘可读 |
| **P3（v2.3，1 个月）** | 图谱可视化（先选型 D3 vs vis-network）；错题自动归因（RAG 形态）；薄弱路径高亮；隐私工程评审 | v2.3 上线门：完整 MVP + 隐私评审通过 |
| **P4（板块三）** | 演示页标注「演示数据」；立项前只做：统计视图层设计、授权位预留、隐私工程评审（最小群体规模）；正式接口（§5.4）不排期 | 规划中 |

---

## 8. 验收标准对照（PRD 12.9 → 工程检查项）

| PRD 验收项 | 工程落点 |
|---|---|
| 三学科错题本+知识库+mastery 端到端 | P1/P2 联调验收脚本 |
| 错题原文/作答/自述错因 100% 不出域（CI 断言） | EgressGuard 单测 + 端到端 payload 抓包断言（pytest + httpx） |
| 知识复盘过 6.3 审核层 | 复用 `safety_filter.py`，补 knowledge 场景用例 |
| 两类复盘入口可区分 | summary-review 分 tab UI 走查 |
| 100 错题 + 1000 mastery P95 < 500ms | mastery 重算异步化 + (user_id, point_id) 索引；压测脚本 |
| LLM 全挂时核心流程可用 | 降级链路测试：录入 / mastery 查看 / 本地模板复盘 |

---

## 附：关键文件索引

- 后端板块二唯一现有代码：`backend/routes/knowledge.py`、`backend/schemas/knowledge.py`、`backend/tests/test_knowledge.py`
- LLM 抽象层：`backend/llm_provider.py`；脱敏：`backend/privacy_filter.py`；审核：`backend/safety_filter.py`
- 状态引擎（mastery 引擎参照物）：`backend/state_engine/`（`state_calculator.py` / `weight_tuning.py`）
- 前端板块二：`frontend/src/pages/Knowledge/index.tsx`、`frontend/src/pages/ErrorBook/index.tsx`、`frontend/src/services/knowledge.ts`、`frontend/src/utils/matchKnowledge.ts`
- 前端板块三雏形：`frontend/src/pages/Community/Upload.tsx`、`Compare.tsx`、`community.ts`
- 扩展点：`frontend/src/components/PersonalData/SectionCard.tsx`、`frontend/src/pages/Settings/index.jsx`（SWITCH_ITEMS）
- 契约：`docs/openapi.yaml`

# 板块二 下一阶段任务细则（W1-3/W2-3/W3-1/W3-2 交付后 · 2026-08-24）

- 版本：v1.0
- 日期：2026-08-24
- 输入文档：`docs/module2-refinement-plan.md`（上一迭代细则，§10 已交付清单）、`docs/module2-backlog.md`、PRD v1.4 §12
- 定位：上一批 4 项已合入（commit `a61d229`），本细则覆盖**剩余全部待办**，按「能否立即开工」分三个阶段重排，不再按原 W1-W4 周次排期
- 与上份细则的差异：本细则每条均经代码现状核实（2026-08-24），修正了上份细则中与代码不符的假设（见各条「现状核实」）

---

## 0. 剩余工作一句话
（2026-08-25 决策更新）算法侧剩 **embedding 启用 → RAG 检索**。经团队评估与协调，embedding 允许适当出域，改为**接入第三方 embedding API**，同时预留**自有服务器模型接入位**（方案见 §0.1）。前端剩 **4 个闭环缺口**（全部纯前端或小契约增量，可立即开工）；工程债剩 **mastery 调权 + 限流持久化**；验收侧剩 **OCR 决策 + 压测/演示/降级矩阵**（需造数）。

### 0.1 本次决策：embedding 走第三方 API + 预留自有服务器

- **背景**：原方案是本地 `bge-small-zh-v1.5`（本地不出域，但需 ~102MB 模型文件，部署重）。团队评估后可**适当出域**，故改用第三方 embedding API（现网通常是可联网拿到的），部署更轻。
- **目标形态**：`embedding_service.py` 保持「local / cloud / off 三模」，新增 `api`（或沿用 `cloud`）模式调用第三方 embedding API；`api` 模式是**全新实现**（当前 `cloud` 分支只是占位返回 None），同时按「**provider 即插即用**」设计预留自有服务器模型接入位——自有模型通常走 OpenAI 兼容 `/embeddings`，届时只需新增一个 provider 配置即可切换。
- **出域边界**：文本向量化把**题干原文**发给第三方（PRD 12.6 的"错题原文不出域"对 LLM 已有豁免，embedding 一并纳入风险评估栏；涉未成年人数据的字段脱敏后再出域，随 PRD §7 数据分类执行）。**向量本身是本地 FAISS 检索，不回传**；检索片段原文**仍不出域**（T8 不变）。
- **统一入口**：`kb_embed_mode` 枚举扩展为 `off | local | api`（可暂不删 `cloud` 字符串，保兼容），由 `embedding_service.embed_text` 暴露；`knowledge_kb.match_points:155` 的 `if mode == "local"` 需同时认 `api`/`local` 两个取值，或改为 `mode in ("local","api")`。
- **现网现状核实（2026-08-25）**：
  - `backend/config.py:41`：仅 `kb_embed_mode: str = "off"`，无第三方 API 密钥/端点配置项，需新增；
  - `backend/embedding_service.py`：三模骨架与 `cloud` 占位分支已就绪（`embed_text:48-51`），但 `api` 模式未实现；且局部逻辑需修（见 T7 改动点）；
  - `backend/routes/knowledge_kb.py:155`：`match_points` 只认 `mode == "local"` 走向量路径，需扩展；
  - **`backend/vector_store.py:37/49`：`search`/`add` 当前是空壳（恒返回空/False），真正的 FAISS 检索/写入尚未实现**——这是"向量匹配真生效"的隐藏前置，即使接入 embedding，不实现它仍是 name_fuzzy。此项在本细则单独列为 T7b，是 T7 的硬依赖。

## 1. 阶段总览

| 阶段 | 内容 | 前置条件 | 建议顺序 |
|---|---|---|---|
| **S0 纯代码项**（可立即开工） | T1-T6：前端 4 项 + 限流持久化 + mastery 调权 | 无 | T1→T2→T3→T4→T5→T6 |
| **S1 算法真实化** | T7 embedding API 接入（+T7b FAISS 实装）、T8 RAG 检索链 | 需第三方 embedding API 凭证；T7b 依赖 FAISS 装库 | T7→T7b→T8（串行，关键路径） |
| **S2 验收与决策** | T9 OCR POC 决策、T10 压测、T11 演示脚本、T12 降级矩阵 | T10/T12 依赖 S1 完成（要测向量降级态） | T9 可随时，T10-T12 收在 S1 后 |

---

## 2. S0 纯代码项（不依赖任何外部资源）

### T1 Recommendations 场景分组（backlog A2 / 原 W2-2）· 1d

- **现状核实**：`frontend/src/types/api.ts:43` 的 `RecScene` 目前**只有** `'post_session' | 'weekly_review'`，上份细则假设的「前端枚举已扩展」不成立，需先扩类型；`pages/Recommendations/index.tsx` 为平铺列表，无分组逻辑。
- **改动点**：
  - `types/api.ts:43`：`RecScene` 增 `'post_session_knowledge'`（与 openapi 对齐，先核对 `docs/openapi.yaml` 中 RecScene 枚举，契约缺的先补契约）；
  - `pages/Recommendations/index.tsx`：列表按 scene 分组渲染，两组标题「状态建议」（post_session / weekly_review）与「内容建议」（post_session_knowledge）；空分组不渲染；
  - 样式沿用现有卡片，不新增设计语言。
- **契约影响**：若 openapi 已含该枚举则无；否则 openapi 先行。
- **测试要求**：typecheck 通过；手动造两类建议数据走查分组与空态。
- **DoD**：两类建议分组可见、样式一致；空分组不占位。

### T2 ErrorBook 编辑表单（backlog A5 / 原 W2-5）· 1.5d

- **现状核实**：`pages/ErrorBook/index.tsx` 无任何编辑入口（grep 无 PATCH/edit）；后端 `PATCH /error-book/{id}` 已就绪。
- **改动点**：
  - `pages/ErrorBook/index.tsx` 详情区加「编辑」入口，弹窗/内联表单编辑三项：错因、状态、关联知识点（知识点选项来自 `services/knowledgeV2.ts`）；
  - `services/errorBook.ts` 增 `updateErrorItem(id, patch)`；
  - 保存成功后本地状态回显；失败保留现有 localStorage 兜底路径（`services/localFallback.ts`）。
- **契约影响**：无（PATCH 已在契约内，动手前先核对字段名与 openapi 一致）。
- **测试要求**：typecheck；手动走查编辑→保存→刷新后一致。
- **DoD**：三字段可编辑保存；断网/失败时降级不白屏、不丢旧数据。

### T3 Goal 表单知识点选择器（backlog A3 / 原 W2-1）· 1.5d

- **现状核实**：`pages/Goals/` 仅 `index.jsx` 单文件（JS），无知识点绑定 UI；契约/ORM/路由已支持 `pointIds`。
- **改动点**：
  - `pages/Goals/index.jsx` 学科类目标表单加知识点多选器，选项取 `GET /knowledge/subjects/{code}/points`（`services/knowledgeV2.ts` 已有封装），随表单学科字段联动刷新；
  - 提交体带 `pointIds`（可空，向后兼容）；目标详情展示已绑定知识点名称。
- **契约影响**：无。
- **测试要求**：手动走查创建/编辑/详情三态；pointIds 为空时行为同现状。
- **DoD**：创建/编辑目标可绑定知识点并在详情可见；非学科类目标不出现选择器。

### T4 知识复盘主动触发入口 + 轮询（backlog A4 / 原 W2-4）· 2d

- **现状核实（2026-08-25 修正）**：`POST /knowledge-summary`（`routes/knowledge.py:148`）是**同步返回 `summary`**（非 202/异步），后端无 `GET /knowledge-summary/{id}`、也无 `insufficient_data` 分支；板块一那套「202 → 轮询 → generation_status」异步链路**没有**用在板块二知识复盘上。前端应按同步语义实现，而非复制板块一轮询。
- **改动点**：
  - SummaryReview 知识 tab 内加「生成本周知识复盘」按钮 + **学科选择**（math/physics/english）→ 直调 `POST /knowledge-summary`，同步把 `summary` 渲染出来；
  - 异常态：429「今日已达上限」、其它错误「生成失败」两类提示，不白屏；
  - service 走 `services/knowledgeSummary.ts`（`createKnowledgeSummary` + `isRateLimited`）。
- **契约影响**：无。
- **测试要求**：手动走查触发→渲染全链路 + 429/其它错误两态。
- **DoD**：用户可选学科并手动触发，看到生成结果；两种异常态均有明确文案，无空白页。

### T5 限流持久化（backlog B5 / 原 W3-4）· 1d（复用 AICallLog 则 0.5d）

- **现状核实**：`_KNOWLEDGE_SUMMARY_DAILY` 是进程内 dict（`routes/knowledge.py:36`），重启即丢；`ai_call_log` 表已就位（上批 W3-2），可按 function_type+日期计数替代。
- **改动点**：
  - `routes/knowledge.py:124-130` 的计数查询/自增改为查 `ai_call_log`（按 `function_type='knowledge_summary'` + 当日计数），或新建独立 `rate_limit` 表 + alembic migration；
  - 注意 W3-1 的系统触发（`jobs/weekly_knowledge_summary.py`）走豁免路径，不得被持久化后误伤——迁移时保持「系统触发不计入用户限额」语义。
- **契约影响**：无。
- **测试要求**：单测：重启（重建 Session/引擎）后计数保留；系统触发不计数；达限返回 429。
- **DoD**：重启后限流计数不丢。

### T6 mastery 调权接入（backlog B2 / 原 W3-3）· 2d

- **现状核实**：`weight_tuning.py` 现有 `alpha/beta ∈ [0.3,0.7]` 与 `w1..w6` 两组权重（LLM 建议 + 区间硬限制 + 留痕），`UserWeightConfig` 持久化；mastery 侧权重组未建。
- **改动点**：
  - `weight_tuning.py` 扩展「内容维度」权重组 α₁..α₅ ∈ [0.1,0.5] 归一化，沿用现有 LLM 建议→区间校验→越界回退→留痕链路；
  - `mastery_engine/` 的 MasteryWeights 改为从 `UserWeightConfig` 读取（现读固定值处替换）；
  - `UserWeightConfig` 增字段 + alembic migration（纯增量、带默认值）；
  - 关闭 AI 调权开关时回退固定权重（沿用现有开关语义）。
- **契约影响**：无（内部权重，不出接口）。
- **测试要求**：单测覆盖：LLM 建议越界回退、归一化校验、留痕写入、开关关闭走固定权重。
- **DoD**：调权链路对 mastery 权重生效、越界回退、留痕可查。

---

## 3. S1 算法真实化（关键路径：第三方 embedding API + FAISS 实装 + RAG）

### T7 接入第三方 embedding API + 预留自有服务器接入位（backlog B3 / 原 W1-1，改走 API）· 2d —— 全迭代第一优先级

> 采纳 2026-08-25 决策：embedding 改为第三方 API（可适当出域），自有服务器模型接入位预留。**不采用本地 bge 模型方案**（本地模型仍可作为 `local` 模式保留在代码里，供无网/离线环境或日后自建时启用，但不在本批次默认启用）。

- **现状核实**：`embedding_service.py` 三模骨架 + `cloud` 占位分支已就绪，但 `api` 模式未实现、`match_points` 只认 `local`、`config` 无第三方 API 配置项、`vector_store` 为空壳（见 **T7b**）。
- **改动点**：
  1. **配置**（`config.py` + `.env.example`）：新增 `embed_api_key`、`embed_base_url`、`embed_model`、`embed_provider`（默认 `openai_compatible`）。沿用现有 LLM 的格式：BASE_URL 指向 `/v1/embeddings` 接口（OpenAI 兼容协议，Bearer 鉴权），KEY 走环境变量，不落库。
  2. **provider 模式**（`embedding_service.py`）：新增 `EmbeddingProvider` 抽象 `embed(text) -> list[float] | None`，两个实现——
     - `ApiEmbeddingProvider`（默认，走第三方 OpenAI 兼容 `/embeddings`，`httpx` 同步/复用现有 `llm_provider` 的 HTTP 客户端与超时配置）；
     - `LocalEmbeddingProvider`（包装现有 `_get_model()` bge），供 `local` 模式/日后自建；
     - provider 选择由 `embed_provider` 决定。**这即是自有服务器接入位**：日后自有模型只需提供 OpenAI 兼容 `/embeddings` 端点，改 `embed_base_url` 即可，无需改 match 链路。
  3. **模式分支**（`embedding_service.embed_text:42-59`）：`mode = embed_mode()` 增 `api` 分支；把 `off → return None` 移回 `try` 内（现位于 `try` 之外），并修 `cloud` 占位分支——`api` 失败/凭证缺失返回 None 走 name_fuzzy 降级，记 warning 日志；`local` 分支保留。
     - 若保留 `cloud` 字符串别名，则 `api` 与 `cloud` 二选一收纳进 provider 判断，避免语义混乱。
  4. **match 链路**（`routes/knowledge_kb.py:155`）：`if mode == "local"` 改为认 `api`/`local`（`mode in ("local","api")`）；`matchedBy` 语义保持（embedding），可加 `source="api"`/`source="local"` 便于区分（写 openapi 时按需）。
  5. **向量一致性**：确保第三方返回维度与 `EMBED_DIM` 对齐（或改从返回体取），写入 FAISS 时以实际维度为准（T7b）。
- **契约影响**：无（`/knowledge/points/match` 形态不变）；若新增 `source` 字段需同步 openapi。
- **测试要求**：
  - 单测：mock HTTP 返回的向量断言 `embed_text` 走向量、`match_points` 走出 embedding 路径；第三方 API 超时/凭证缺失/非 200 时降级 name_fuzzy 且不报错、有日志；
  - 手动/集成：用真实第三方凭证跑一遍，错题录入 → 知识点建议 Top-5 语义相关率 ≥3/5 为通过；
  - provider 两分支（api/local）各跑一次。
- **DoD**：`kb_embed_mode=api` 下错题录入→知识点建议走向量 Top-5；API 挂时降级 name_fuzzy；自有服务器接入位可用（改 `embed_base_url` 即切换）；启动无本地大模型加载（比本地方案轻，无模型打包成本）。
- **依赖**：T7b（FAISS 实装）；第三方 embedding API 凭证。

### T7b FAISS 检索/写入实装（backlog B3 隐藏前置 · 2026-08-25 新列）· 1.5-2d

- **现状核实**：`vector_store.py:37 search` 与 `:49 add` 当前是空壳（恒返回 []/False），`_index_root()` 的索引目录逻辑已就位，`kb_embeddings` 参考表已存在（由错误本 API 写入）。这是「从链路通到向量真生效」的隐藏阻塞：**即使 embedding 接入，不实现 FAISS 则匹配仍走 name_fuzzy**。
- **改动点**：
  - `vector_store.add`：用 `faiss.IndexFlatIP` 建索引 + 存 `vector_id ↔ ref` 映射（内存 + 可选 `.faiss`/`.npz` 落盘到 `_index_root()`，MVP 可仅内存、重建时从 `kb_embeddings` 表重灌）；`model`/`dim` 参数记录到引用，支持不同模型维度隔离。
  - `vector_store.search`：`index.search(vec, top_k)` 返回 `[(ref_id, similarity)]`；索引缺失/FAISS 未装返回 []（现状语义保留，调用方 name_fuzzy 兜底）。
  - 写入时机：现有写 `kb_embeddings` 的调用点（`knowledge_kb`/`knowledge.py` 落知识库时）同步调 `add`；`faiss-cpu` 确认在 `pyproject` 主依赖。
- **契约影响**：无。
- **测试要求**：单测：`add` 若干 → `search` 命中 Top-K 且相似度递减；重建后索引可从 `kb_embeddings` 重灌；FAISS 缺席时返回空不抛错。
- **DoD**：有真实向量的知识点可被向量检索命中；无向量/FAISS 挂时 name_fuzzy 兜底。
- **依赖**：无（可与 T7 并行实现，T8 E2E 前两者须都完成）。

### T8 RAG 检索链接通（backlog C5 / 原 W1-2）· 2d · 依赖 T7 + T7b

- **现状核实**：`routes/knowledge.py:250 _build_error_parse_prompt` 已按 error_id 本地检索关联知识点，且出域压缩为「知识点名 + 定义」（`retrievedFragmentSnippets` 已在白名单 `egress_guard.py:54`）。**缺的是**：题干 rawText 向量化 → kb_points 检索 Top-K 这一步（当前只查错题已绑定的点，未绑定时检索为空、走中性提示）。
- **改动点**：
  - `_retrieve_error_points` 增「rawText → embed_text → vector_store.search(subject=...) Top-K → 片段元信息组装」路径，与既有按 error_id 关联点取并集去重；
  - 出域 payload 仍只含 pointName/pointDefinition 等元信息——**片段原文属 PRD 12.6 禁止出域项，不得放入 prompt 与 egress**；
  - embedding off/失败时保持现状（按关联点检索或中性提示），不报错。
- **契约影响**：无（接口形态不变）。
- **测试要求**：E2E——embedding on 录入错题 → error-parse → `test_egress_ci.py` 拦截规则全绿；检索相关性人工抽 10 条评估。
- **DoD**：error-parse 出域 = 检索知识点名称/定义/易错点 + 错因候选，无任何原文；`data_class=knowledge_aggregated` 声明完整。

---

## 4. S2 验收与决策

### T9 OCR 真实识别决策（backlog C4 / 原 W1-4）· 2d · 只做决策不做实现

- 产出：一页 POC 结论——PaddleOCR 本地跑数学公式/中英文混排识别率数据 + 「进入下一迭代 / 延期到板块二上线后」结论；更新 `routes/ocr.py` docstring 与 backlog C4 状态。

### T10 性能压测（C2 / 原 W4-1）· 2d · 建议 S1 后做

- 造数：单用户 100 错题 + 1000 mastery 记录；脚本压 `/error-book` 列表、`/mastery/subjects/{code}`、graph 接口；
- **DoD**：P95 < 500ms（PRD 12.9）；图谱初渲染 < 1s；不达标执行预案（graph 分页/懒加载、B4 并发队列提前）。

### T11 演示脚本固化（C3 / 原 W4-2）· 1.5d

- 5 核心场景（知识库浏览/错题录入建议/复习/mastery 展示/知识复盘）脚本化走查 + 纳入回归；可重复执行、结果留档。

### T12 降级链路矩阵（原 W4-3）· 2d · 依赖 T7/T7b/T8（要覆盖向量与 API 挂的场景）

- embedding API 挂 / LLM 挂 / 向量库(FAISS)挂 / 网络断 四态 × 核心流程；断言无空白页、均有降级提示；计划书 §8 验收清单 6 项逐条打勾。

### 上线门（不变，对齐 PRD 12.9）

T10/T11/T12 全绿 + D2/D4 法务通过 + 错题原文 100% 不出域 CI 断言绿。非代码项 D1-D4 沿用原细则第 6 节并行推进。

---

## 5. 排期建议

```
第1周          第2周                第3周
T1 分组(1d)    T5 限流(1d)          T10 压测(2d)
T2 错题编辑(1.5d) T6 调权(2d)       T11 演示脚本(1.5d)
T3 目标选择器(1.5d) T7 embedding-API(2d)+T7b FAISS(2d) T12 降级矩阵(2d)
T4 复盘触发(2d)     T8 RAG(2d)        T9 OCR 决策(穿插)
```

- 关键路径：**T7 → T7b → T8 → T12**；S0 六项与 S1 可并行。T7 改走第三方 API 后**无需本地模型下载**，T7 与 T7b 可先行（T7b 只需装 `faiss-cpu`），是当前最快能推动的算法进度点。
- 若只有一人：按 T1→T2→T3→T4→T5→T6→T7→T7b→T8→T9→T10→T11→T12 顺序，约 22 人日。

## 6. 与既有文档的关系

- 状态追踪以 `docs/module2-backlog.md` 为准，每完成一项回写状态列；
- 契约变更先改 `docs/openapi.yaml`（本阶段仅 T1 可能涉及 RecScene 枚举核对，其余零契约改动）；
- 完成后在本文件追加「已交付项」章节，格式沿用 `module2-refinement-plan.md` §10。

---

## 7. 已交付 / 修复项

| 编号 | 项 | 交付批次 | 摘要 |
|---|---|---|---|
| T1-T6 | S0 纯代码项 | PR #37（`b894062`） | 前端分组/错题编辑/目标选择器/复盘触发 + 限流持久化 + mastery 调权读取侧 |
| T2 修复 | 错题编辑 status 回显 + pointIds 提交 | 本批（验收后修复） | `ErrorItem` 增 `status`/`pointIdByName`；`openEdit` 回显实际状态；PATCH 携带反查的 `pointIds` |
| T4 修复 | 复盘学科选择 | 本批 | 去掉硬编码 `math`，加 math/physics/english 下拉；按同步返回语义实现（非 202+轮询） |
| T6 补全 | mastery 调权写入侧 | 本批 | `_suggest_weights` 扩展 m1..m5；`_validate_mastery_weights` 区间/归一化/单次变动校验；`WeightAdjustLog` 增 before/after_m* 快照列 + 迁移 `a1b2c3d4e5f6`；落库留痕 |
| T7 | embedding 第三方 API 接入 | 本批 | config 增 `embed_api_key/base_url/model`（OpenAI 兼容 `/v1/embeddings`）；`embedding_service.embed_text` 增 `api` 分支（超时/重试/配置缺失均降级 name_fuzzy）；`match_points` 认 `local/api`；自有服务器接入位=换 base_url/model 即可 |
| T7b | FAISS 实装 | 本批 | `vector_store.py` IndexFlatIP + L2 归一化（内积=余弦）+ 落盘持久化（`kb_vectors/`）+ `rebuild_index`；`_async_embed_error` 挂 `add`；`pyproject` 补 `faiss-cpu` |
| D1(表) | 知识点库建表（7 内容列） | 本批（先建表，导入后续） | `kb_points` 增 `explanation/frequency/typical_errors(JSON)/example/keywords(JSON)/module_path/source_version`；ORM + JSON helper；`KnowledgePointDetail` 加 7 可选字段 + validators；openapi 同步；`get_point` 填充；迁移 `c0ffee123456`；conftest 探针。`prerequisites` 复用 `kb_point_relations` 不建列 |

### 真实联调（2026-08-25，智谱 embedding-3）

- 接入：`KB_EMBED_MODE=api` + 智谱 `open.bigmodel.cn/api/paas/v4` + `embedding-3`，真实返回 **2048 维**向量。
- 过程：lmuai 网关上游故障（`upstream authentication failed` + 模型列表空）→ 改用智谱，key 换为智谱令牌后成功。
- 结果（6 个数学知识点种子，库已清理）：
  - 向量检索 4/4 查询 Top-1 命中（单调 / 等差 / 极值 / 数量积），相似度区分度明显（Top-1 vs Top-2 间隔 ≥0.1）；
  - HTTP `/points/match` 三条查询均 `matchedBy=embedding`，Top-1 全部正确——**真实 embedding 全链路（录入→入库→检索→路由）跑通**。
- 质量门：语义相关率 4/4 ≥ 3/5，**通过**。
- key 只写本地 `backend/.env`（gitignore，未跟踪），未泄入仓库。

### T8 RAG 检索链（已交付 2026-08-25）

- `routes/knowledge.py` `_retrieve_error_points` 增向量召回路径：错题原文向量化 → FAISS 召回（point 类型 ref 直接取知识点 / error 类型 ref 取其关联知识点）→ 与已绑定知识点并集去重；学科过滤 + embedding 失败静默降级。
- 出域保持只含 `pointName/pointDefinition`（`retrievedFragmentSnippets`），prompt 内元信息含易错点，**原文不出域**（`test_egress_ci.py` 规则不变全绿）。
- 顺带修复：路径 1 原 SQL 返回 `definition/error_tip` 可能为 None 导致 f-string 输出 "None" 的问题（`or ""`）。
- 验证：5 个新单测（绑定路径 / point ref 召回 / error ref 召回 / 向量失败降级 / 跨学科过滤）；真实 E2E——未绑定知识点的错题「求等差数列前 n 项和时公式记错了」向量召回 Top-2 = 数列求和、等差数列，语义正确；全量 234 passed / 1 skipped / 1 failed（失败为无关 SMTP 用例）。
- 依赖说明：知识点向量化写入时机待 D1 内容导入（当前 FAISS 以错题向量为主，召回路径已兼容两种 ref 类型，D1 后自动增强）。

- 细则修正：T4 原假设「POST 202 → 轮询 GET /knowledge-summary/{id}」过时——后端 `POST /knowledge-summary` 实际**同步返回 summary**，前端按同步语义实现。


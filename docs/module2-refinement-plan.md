# 板块二 完善计划细则（PR #35/#36 交付后 · 下一迭代）

- 版本：v1.1
- 日期：2026-08-24（v1.1 同日追加「已交付」状态）
- 输入文档：`docs/module2-backlog.md`（团队 backlog，执行层真源）、`docs/module2-3-as-built-vs-plan.md`（计划 vs 实际偏差）、PRD v1.4 §12、PRD 12.9 验收标准
- 定位：本细则是 `module2-backlog.md` 的**可执行展开**——每条 backlog 落到具体文件改动点、契约影响、测试要求与 DoD；不重复 backlog 的优先级结论，只补执行细节
- 阅读对象：后端、前端、QA

> **交付状态（2026-08-24）**：W1-3 薄弱路径高亮、W2-3 StudyGuide 短板提示、W3-1 自动周复盘、W3-2 AICallLog 持久化已实现并合入（见文末 §10）。W1-1/1-2（embedding/RAG）依赖真实模型，W1-4（OCR）与 W4（压测）依赖 POC/造数，未在本批次执行。

---

## 0. 当前状态一句话

核心链路（知识库/错题本/mastery/复盘/出域合规）已跑通但**算法价值未真实生效**（embedding off、RAG 未接、调权未接），前端 5 个闭环缺口未补，验收类工作（压测/演示/降级矩阵）未执行——本迭代目标：**从"链路通"到"算法真生效 + 前端闭环 + 可上线"**。

## 1. 迭代目标与里程碑

| 里程碑 | 目标 | 周期建议 |
|---|---|---|
| **M1 算法真实化** | embedding 真实启用 + RAG 检索链接通 + 薄弱路径高亮 | 第 1 周 |
| **M2 前端闭环** | backlog A1-A5 全部收口 | 第 2 周 |
| **M3 验收上线** | 工程债关键项 + 压测/演示/降级矩阵 + 验收清单全绿 | 第 3 周 |

非代码项（D1-D4）随迭代并行，法务两项卡 M3 上线门。

---

## 2. W1 真实算法链路（最高优先）

### W1-1 启用本地 embedding（backlog B3）

- **改动点**：
  - `backend/config.py:41`：`kb_embed_mode` 由 `off` → `local`（通过环境变量切换，不改默认值，避免影响 CI/无模型环境）；
  - `backend/embedding_service.py`：验证 bge-small-zh-v1.5 懒加载路径（`sentence-transformers` 延迟 import 已就位）；补"模型文件缺失"的明确报错与降级日志；
  - 部署文档：模型获取与打包方案（镜像 +~102MB，或挂载卷），写入 `docs/`；
  - `backend/pyproject.toml`：确认 `faiss-cpu` 已在依赖（PR #35 已加），`sentence-transformers` 建议放 optional extra（`pip install .[embed]`）。
- **契约影响**：无（接口形态不变，`/knowledge/points/match` 内部从 name_fuzzy 切向量）。
- **测试要求**：
  - 单测：mock embedding 模型，断言 match 走向量路径；模型文件缺失时降级 name_fuzzy 且不报错；
  - 手动对比：同一题干文本分别跑 name_fuzzy 与向量模式，Top-5 命中率人工评估（≥3/5 语义相关为通过）。
- **DoD**：`kb_embed_mode=local` 下错题录入→知识点建议走向量 Top-5；name_fuzzy 作为降级保留；启动时间增量 < 3s（懒加载）。
- **估时**：3d（含模型验证与文档）。**依赖**：无。**这是全迭代第一优先级**——向量质量不达标则 W1-2/W1-3 价值打折。

### W1-2 RAG 检索链接通（backlog C5）

- **改动点**：
  - `backend/routes/knowledge.py` error-parse 链路：当前已按 errorId 本地取错题，补「rawText 向量 → kb_points 检索 Top-K → 片段元信息组装」步骤；
  - 出域 payload 只含白名单字段（`retrievedFragmentSnippets` 已在 EgressGuard 白名单，`egress_guard.py:54`）——注意片段**元信息**（pointName/定义/易错点）可出域，片段原文是否出域需按 PRD 12.6 复核：检索片段原文属禁止项，仅片段的**知识点归属与定义**可出域；
  - 依赖 W1-1（向量库有真实向量才可检索）。
- **测试要求**：E2E——录入错题（embedding on）→ 触发 error-parse → 断言出域 payload 经 `test_egress_ci.py` 拦截规则全绿；检索结果与录入知识点相关性人工抽 10 条评估。
- **DoD**：error-parse 出域内容=检索到的知识点名称/定义/易错点+错因候选，无任何原文；`data_class=knowledge_aggregated` 声明完整。
- **估时**：2d。**依赖**：W1-1。

### W1-3 薄弱路径高亮（backlog C1）

- **改动点**：
  - 后端：`GET /knowledge/subjects/{code}/graph`（`routes/knowledge_kb.py:245`）响应增 `weakPointIds`（当前用户该学科下 `mastery<0.4 且 data_sufficient=true` 的知识点 id 列表）——纯增量字段，向后兼容；
  - 前端：`frontend/src/pages/Knowledge/Graph.tsx` 对 weakPointIds 节点叠加描边/光晕样式（vis-network `borderWidth`/`shadow`），与 mastery 色阶并存；
  - 契约：openapi.yaml graph 响应 schema 增 `weakPointIds: string[]`。
- **测试要求**：单测断言 weakPointIds 计算逻辑（mastery<0.4 且样本足）；前端手动走查。
- **DoD**：有未掌握知识点的学科图谱上可见高亮叠加；无数据学科不报错、无高亮。
- **估时**：2d（前后端各 1d）。**依赖**：无硬依赖， mastery 数据越真实效果越好（建议排在 W1-1 后）。

### W1-4 OCR 真实识别决策（backlog C4）

- **本迭代只做决策不做实现**：PaddleOCR 本地 POC（数学公式/中英文混排识别率）或宣布延期到板块二上线后。
- **产出**：一页 POC 结论（识别率数据 + 是否进入下个迭代），更新 `routes/ocr.py` docstring 与 backlog C4 状态。
- **估时**：2d（POC）。**依赖**：无。

---

## 3. W2 前端闭环（backlog A1-A5）

> 顺序按团队 backlog 建议：A3+A2 → A1+A4 → A5。后端依赖均已就绪，全部为纯前端或"前端+小契约增量"。

### W2-1 Goal 表单知识点选择器（A3）

- **改动点**：`frontend/src/pages/Goals/` 目标表单（学科类目标）加知识点多选器，数据来自 `GET /knowledge/subjects/{code}/points`（`services/knowledgeV2.ts` 已有）；提交时带 `pointIds`（契约/ORM/路由已就绪）。
- **DoD**：创建/编辑目标可绑定知识点；详情可见绑定；向后兼容（pointIds 可空）。
- **估时**：1.5d。

### W2-2 Recommendations 场景分组（A2）

- **改动点**：`frontend/src/pages/Recommendations/index.tsx` 列表按 scene 分组渲染，新增 `post_session_knowledge` 分组标签（"内容建议"与"状态建议"并列）；RecScene 枚举前端已扩展，仅缺分组 UI。
- **DoD**：两类建议分组可见、样式一致；空分组不渲染。
- **估时**：1d。

### W2-3 StudyGuide「建议先补」短板提示（A1）

- **改动点**：
  - 后端：`routes/plan.py` `create_plan`（:221）响应的 Plan schema 增 `weaknessHints: [{ pointId, pointName, mastery }]`（查该用户该学科 mastery<0.7 按升序取 Top-3）——**契约增量**，openapi.yaml Plan schema 同步；
  - 前端：`pages/StudyGuide/index.jsx` 渲染"建议先补：函数·单调性（当前掌握 55%）"提示条；无数据时不渲染（冷启动兼容）。
- **测试要求**：后端单测（有/无 mastery 数据两态）；前端占位/缓存降级沿用 `usePanelData` 模式。
- **DoD**：有短板数据的用户生成计划时可见提示；新用户无感知。
- **估时**：2d（前后端各 1d）。

### W2-4 知识复盘主动触发入口 + 轮询（A4）

- **改动点**：
  - 前端：`SummaryReview/index.tsx` 知识 tab 内加"生成本周知识复盘"按钮（选学科）→ `POST /knowledge-summary`（202）→ 轮询 `GET /knowledge-summary/{id}` 至 `generation_status=ready`（后端字段已存在，`routes/knowledge.py:183`）→ 渲染；429 限流提示"今日已达上限"；
  - 复用板块一复盘轮询组件模式（SummaryReview 已有轮询逻辑可参照）。
- **DoD**：用户可在知识 tab 手动触发并看到生成全过程；限流/失败/数据不足三态均有提示。
- **估时**：2d。

### W2-5 ErrorBook 编辑表单（A5）

- **改动点**：`pages/ErrorBook/index.tsx` 详情加编辑入口（错因/状态/关联知识点修改 → `PATCH /error-book/{id}`，后端已就绪）；编辑后本地状态回显。
- **DoD**：三项字段可编辑保存；失败回退 localStorage 兼容路径不破坏。
- **估时**：1.5d。

---

## 4. W3 后端工程债

### W3-1 自动周复盘定时任务（计划书 2.2-4 遗留，backlog 未列——本细则补录）

- **改动点**：新增 `backend/jobs/weekly_knowledge_summary.py`：每日扫描，对「该学科本周 ≥3 条学习/错题记录」的用户触发 knowledge-summary 生成（复用现有链路，跳过已生成过的周期）；用 FastAPI startup 挂 `asyncio` 定时器即可（MVP 单机，不引 APScheduler）。
- **测试要求**：单测覆盖触发条件（≥3 条 / 跨周去重 / 限流豁免——系统触发不计入用户每日限额）。
- **DoD**：满足条件用户周一打开 summary-review 能看到自动生成的知识复盘。
- **估时**：2d。

### W3-2 AICallLog 持久化（B1，PRD 6.5 上线前必须）

- **改动点**：`models/` 新增 `AICallLog`（function_type、data_class、input_digest、latency_ms、success、egress_blocked、cost_units、created_at）+ alembic migration；`llm_provider.py` 与 EgressGuard 拦截点写入。
- **DoD**：每次 LLM 调用/拦截均有 DB 记录；不含用户身份信息（PRD §7 铁律）；可按用户/功能聚合查询（6.4 成本监控数据源）。
- **估时**：2d。

### W3-3 mastery 调权接入（B2）

- **改动点**：`weight_tuning.py` 扩展「内容维度」权重组（α₁..α₅ ∈ [0.1,0.5] 归一化，沿用现有区间硬限制与留痕表）；周期调权时同步处理；MasteryWeights 从 UserWeightConfig 读取。
- **DoD**：调权链路对 mastery 权重生效、越界回退、留痕可查；关闭 AI 调权时固定权重。
- **估时**：2d。

### W3-4 限流持久化（B5）

- **改动点**：`_KNOWLEDGE_SUMMARY_DAILY` dict → DB 表（或复用 AICallLog 计数）；
- **DoD**：重启后限流计数不丢。
- **估时**：1d（随 W3-2 顺带做，共用表则 0.5d）。

### W3-5 进程内并发队列（B4）

- **本迭代不做**，保留 backlog；触发条件：压测（W4-1）发现 BackgroundTasks 成为瓶颈时再排。

---

## 5. W4 验收与上线门（M3）

| # | 任务 | 内容 | DoD | 估时 |
|---|---|---|---|---|
| W4-1 | 性能压测（C2） | 造数：单用户 100 错题 + 1000 mastery 记录；locust/脚本压 `/error-book` 列表、`/mastery/subjects/{code}`、graph 接口 | P95 < 500ms（PRD 12.9）；图谱初渲染 < 1s（ADR 自设目标，一并测） | 2d |
| W4-2 | 演示脚本固化（C3） | 5 核心场景（知识库浏览/错题录入建议/复习/mastery 展示/知识复盘）脚本化走查 + 纳入回归 | 脚本可重复执行，结果留档 | 1.5d |
| W4-3 | 降级链路矩阵 | embedding 挂 / LLM 挂 / 向量库挂 / 网络断 四态 × 核心流程；断言无空白页、均有降级提示 | 矩阵全绿；计划书 §8 验收清单 6 项逐条打勾 | 2d |
| W4-4 | 板块二隐私工程评审 | EgressGuard 链路走查 + CI 断言复核 + 出域边界 12.6 强化版对照 | 评审纪要归档，无 P0/P1 遗留 | 评审周 |

**上线门（对齐 PRD 12.9）**：W4-1/2/3 全绿 + D2/D4 法务通过 + 错题原文 100% 不出域 CI 断言绿。

---

## 6. W5 非代码项（并行）

| # | 项 | 负责 | 时间 |
|---|---|---|---|
| D1 | 数学 50 / 物理 100 / 英语 200 正式内容清单替换示例种子 | 内容运营 | 第 2 周前 |
| D2 | 监护人授权文案 v1.5（板块二专款）法务评审 | 法务+产品 | M3 上线门前 |
| D3 | 复盘生成内容每周人工抽检流程建立 | 运营 | M3 起持续 |
| D4 | 出域边界 12.6 强化版法务评审 | 法务 | M3 上线门前 |

---

## 7. 排期与人力

```
        第1周 (M1)            第2周 (M2)            第3周 (M3)
后端    W1-1 embedding(3d)    W3-1 周复盘(2d)       W4-1 压测(2d)
        W1-2 RAG(2d)          W3-2 AICallLog(2d)    W4-3 降级矩阵(1d)
                              W3-3/3-4 调权+限流(2.5d)
前端    W1-3 高亮(1d)         W2-1/2-2 (2.5d)       W4-2 演示脚本(1.5d)
        W2-3 后端联调         W2-4/2-5 (3.5d)       修复 buffer
QA      W1 测试用例           W2 走查               W4 全量执行
```

- 人力：1 后端 + 1 前端 + 0.5 QA，3 周；后端约 15 人日，前端约 10 人日，QA 约 7 人日。
- 关键路径：**W1-1（embedding 启用）→ W1-2（RAG）→ W4-3（降级矩阵含向量场景）**；其余可并行。

## 8. 风险与应对

| 风险 | 等级 | 应对 |
|---|---|---|
| bge-small-zh 向量匹配质量不达标（Top-5 语义相关率 <60%） | 高 | W1-1 设质量门：不达标则回退 name_fuzzy 上线，向量作为实验开关；同时评估 m3e-small 备选（ADR 已留位） |
| 模型打包体积影响部署（+~102MB） | 中 | optional extra + 挂载卷方案二选一，部署文档写明；CI 环境不装模型 |
| 正式内容清单延期（D1） | 中 | 示例种子可撑演示；M3 上线门不强制正式内容，但对外演示话术需注明 |
| 法务评审延期（D2/D4） | 高 | 功能可开关关闭（knowledge_ai_egress_enabled 默认关），不阻塞其余上线 |
| 压测不达标（P95>500ms） | 中 | 预案：mastery 重算已异步；graph 接口加分页/懒加载；B4 并发队列提前排期 |

## 9. 与既有文档的关系

- 执行状态追踪以 `docs/module2-backlog.md` 为准，本细则每完成一项回写 backlog 状态列；
- 契约变更（W1-3 weakPointIds、W2-3 weaknessHints）先改 openapi.yaml 再实现（契约先行铁律）；
- 验收口径以 PRD 12.9 + 计划书 §8 为最终标准。

## 10. 已交付项（2026-08-24）

| 编号 | 项 | 改动摘要 | 测试 |
|---|---|---|---|
| W1-3 | 薄弱路径高亮 | openapi `KnowledgeGraph.weakPointIds`；`mastery_engine.gather_inputs/compute_weakness_hints` 抽出公共函数；`knowledge_kb.get_graph` 计算 mastery<0.4 且样本足的点；前端 `Graph.tsx` 弱节点描边+光晕 | `test_weakness_hints.py` |
| W2-3 | StudyGuide 短板提示 | openapi `PlanWeaknessHint` + `Plan.weaknessHints`；`plan.create_plan` 查 mastery<0.7 升序 Top-3；前端 `StudyGuide` 提示条 + 样式 | `test_weakness_hints.py` |
| W3-1 | 自动周复盘 | `jobs/weekly_knowledge_summary.py`：本周 ≥3 条记录触发、跨周去重、系统触发不限流；`main.py` lifespan 挂 asyncio 定时器 | `test_weekly_summary_job.py` |
| W3-2 | AICallLog 持久化 | `models/ai_call_log.py`（无身份字段）+ alembic `a6b5c4d3e2f1`；`ai_call_log.py` 写入器 + `llm_provider` 接入（含 egress 拦截留痕） | `test_ai_call_log.py` |
| — | 修 vis-network 版本 | PR #36 误写 `^10.1.2`（不存在），改为 `^10.1.0`，修复 `npm install` 失败 | 前端 typecheck 通过 |

- 验证：后端全量 212 passed / 1 skipped / 1 failed（唯一失败为无关的 SMTP 邮件用例，环境依赖且 flaky）；前端 `npm run typecheck` 通过。
- 未在本批次：W1-1/1-2（需真实 embedding 模型）、W1-4（OCR POC）、W4-1/2/3（压测/演示/降级矩阵，需造数）、W2-1/2-2/2-5（前端纯增强，未在本次范围）。

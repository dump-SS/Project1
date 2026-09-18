# 板块二/三「计划 vs 实际交付」对比（as-built vs plan）

> **阶段口径说明（2026-08-29 补记）**
>
> 本文档作为「计划 vs 实际交付」的对照基线**仍然有效**，其中记载的交付事实与偏差分析均以当时为准，不做改写。
>
> 但文档中引用的阶段口径（「法务评审」「上线门」「上线前必须」等）按当时的**正式发布尺度**书写，**不代表当前 pilot 口径**。项目当前处于 pilot 阶段，由学生团队维持，无外部评审资源；现行口径见仓库根目录 `PRD-学习状态智能助手.md` 文首「关于阶段口径」一节，按「设计底线 / 团队内完成 / 记入待办」三档执行。

- 版本：v1.0
- 日期：2026-08-24
- 对比对象：`docs/module2-3-development-plan.md`（2026-08-23 计划书）与远端 main 实际交付（PR #35 `408180b` + PR #36 `14dc17f`，2026-08-24 合并）
- 说明：计划书完成于团队开发启动前；两份 ADR（`adr-vector-embedding.md`、`adr-graph-visualization.md`）与 `module2-backlog.md` 均显式引用了计划书与差距清单的章节号，表明团队以计划书为实施蓝本。本文档为审计留痕与后续 backlog 排期的对照基线。

---

## 1. 总览：计划 16 周 → 实际 1 天（两批 PR）

| 计划书阶段 | 计划周期 | 实际交付 | 交付 PR | 状态 |
|---|---|---|---|---|
| P0 地基与合规 | 第 1-2 周 | 全部落地 | #35 | ✅ 完成 |
| v2.1 数学单科端到端 | 第 3-8 周 | 全部落地 | #35 | ✅ 完成 |
| v2.2 学科扩展 | 第 9-12 周 | 主体落地，2 项降级 | #35 | ⚠️ 完成（有偏差，见 §4） |
| v2.3 体验升级 | 第 13-16 周 | 图谱/归因形态落地，3 项未做 | #36 | ⚠️ 部分完成 |
| 板块三预留 | 不排期 | 全部预留项落地 | #36 | ✅ 完成 |

实际交付规模：72 个文件、+5776 / -372 行；pytest 203 passed / 1 skipped；前端 typecheck、vite build 通过。

---

## 2. P0 阶段对照（计划书 §3）

| 计划项 | 计划内容 | 实际交付 | 判定 |
|---|---|---|---|
| P0-1 违规接口整改 | /error-parse、/knowledge-summary 加鉴权+脱敏+审核+留痕 | **超出预期**：/error-parse 直接重构为 errorId 引用形态（原文只本地检索，出域仅 knowledge_aggregated 白名单字段），prompt 重写为「只能基于知识点片段与错因候选分析，不得引用原文」；/knowledge-summary 加 `current_user` + 结构化入参 + 202 异步 + 落 summaries + 每日限流（429 RATE_LIMITED） | ✅ 优于计划 |
| P0-2 契约 v1.5 | 17 条板块二 API + 错误码 + 漂移修复 | openapi.yaml 升至 **1.5.0**，17 条 API 全部定义（另加 2 条 community planned），KB 错误码 3 个，4 条契约漂移补录 | ✅ 一致 |
| P0-3 alembic | 基线化 + 迁移规范 | `backend/alembic/` 全套 + **5 个 revision**（baseline / kb_* 8 表 / settings egress 列 / summaries.dimension / goals.point_ids） | ✅ 一致 |
| P0-4 EgressGuard | data_class 三级 + 拒绝序列化 + audit log | `backend/egress_guard.py`：默认拒绝策略、嵌套递归扫描、白名单 frozenset（25 键）、raw 字段黑名单（15 个字段名含 snake/camel 双写）；provider 层兜底；板块一 4 处调用迁移为 `state_plan`（PR #36） | ✅ 一致，白名单键设计更完整 |
| P0-5 选型 ADR | FAISS + bge-small-zh 倾向，POC 后决策 | `adr-vector-embedding.md`：FAISS + bge-small-zh-v1.5（与计划一致）；`adr-graph-visualization.md`：vis-network（计划要求 POC 后定，团队直接选型并记录理由） | ✅ 一致（图谱跳过 POC，见 §4） |
| P0-6 法务评审 | 启动 | 未完成（列入 backlog D2/D4） | ⚠️ 非代码项，按预期挂起 |
| P0-7 内容运营 | 数学 50 点清单 | 种子脚本已建（`scripts/seed_kb_math.py` 209 行 + 物理/英语示例），但**正式内容清单仍是示例数据**（backlog D1） | ⚠️ 工程就绪，内容待正式交付 |
| CI 出域断言 | pytest 抓包断言 raw 不出域 | `tests/test_egress_ci.py` + `tests/test_egress_guard.py` 落地 | ✅ 一致 |

---

## 3. v2.1 / v2.2 / v2.3 对照

### v2.1（计划书 §4）—— 全部落地

| 计划项 | 实际 | 判定 |
|---|---|---|
| kb 三表建模 + 种子 | `models/knowledge.py`（147 行）+ 幂等种子脚本 | ✅ |
| 知识库 5 只读 API | `routes/knowledge_kb.py`（268 行）；match 在 embedding 未启用时降级 `name_fuzzy`（与计划"接口形态不变"策略一致） | ✅ |
| embedding/向量库封装 | `embedding_service.py` + `vector_store.py` 落地，但**默认 `kb_embed_mode=off`**，未真实启用（见 §4 偏差 1） | ⚠️ |
| 错题本 CRUD + 软删 + 敏感词 | `routes/error_book.py`（344 行），KB_TEXT_TOO_LONG、软删、敏感词阻断、异步 embedding hook 全部就绪 | ✅ |
| mastery 引擎 + 2 API | `mastery_engine/`：五因子公式、α₁..α₅ 等权初始、MIN_SAMPLES=3 置信度规则——与计划设计逐条一致 | ✅ |
| 设置出域开关 | `knowledge_ai_egress_enabled`（settings 列迁移 + Settings 页开关） | ✅ |
| Knowledge/ErrorBook/MasteryCard 转正 | 三个前端改造全部落地；ErrorBook 失败时回退 localStorage（"不静默"标注保留） | ✅ |

### v2.2（计划书 §5）—— 主体落地，2 项降级

| 计划项 | 实际 | 判定 |
|---|---|---|
| summaries.dimension + 知识复盘落库 | 落地（202 异步 + dimension=knowledge + 每日限流） | ✅ |
| 学科级自动周复盘定时任务 | **未见实现**（backlog 未列；前端 A4 也缺主动触发入口） | ❌ |
| 艾宾浩斯复习 | `POST /error-book/{id}/review` + 复习 UI（记住了/没记住 + 下次复习时间） | ✅ |
| OCR 录入（真实识别） | **降级为 501 接口占位**（`routes/ocr.py`，手动录入保底；ADR 记为实验功能） | ⚠️ 偏差，见 §4 |
| mastery 调权链路 | 引擎支持权重参数，**周期调权调度未接**（backlog B2） | ❌ |
| mastery timeline | 真实实现 | ✅ |
| SummaryReview 分 tab / post_session_knowledge / Goal.pointIds | 全部落地（PR #36） | ✅ |

### v2.3（计划书 §6）—— 图谱与归因形态落地，3 项未做

| 计划项 | 实际 | 判定 |
|---|---|---|
| 图谱可视化 | vis-network 直接选型落地（`Knowledge/Graph.tsx`，mastery 色阶 + 点选联动） | ✅（跳过 POC） |
| 错题自动归因（合规 RAG 形态） | error-parse 合规形态就位（errorId 引用 + 白名单出域），但 **RAG 检索链未接真实 embedding**（backlog C5） | ⚠️ |
| 薄弱路径高亮 | 未做（backlog C1） | ❌ |
| 性能压测 P95<500ms | 未执行（backlog C2） | ❌ |
| 5 核心场景演示脚本固化 | 未执行（backlog C3） | ❌ |
| 隐私工程评审 | 板块二部分随 PR 完成；板块三预评审纪要已出（`module3-privacy-review.md`，结论"中等偏高，不立项"） | ✅ 部分 |

### 板块三预留（计划书 §7）—— 全部落地且超出

| 计划项 | 实际 | 判定 |
|---|---|---|
| 3-A 演示页标注 | `CommunityDemoBadge` 组件落地 | ✅ |
| 3-B 统计视图层设计 | `module3-statistics-view-design.md`：k≥20、`COMMUNITY_INSUFFICIENT_POOL`、只发聚合不发个体、授权可撤回 | ✅ 超出计划（给出了具体错误码与数据流图） |
| 3-C 隐私预评审 | 7 项风险逐条定级 + 4 条放行条件 | ✅ 超出计划 |
| 3-D 契约 planned | `/community/features`、`/community/aggregate` 已入 openapi（x-status: planned） | ✅ |

---

## 4. 计划与实际的关键偏差分析

| # | 偏差 | 影响 | 评价 |
|---|---|---|---|
| 1 | **embedding 默认 off，真实向量检索未启用**（`kb_embed_mode=off`，全链路走 name_fuzzy 降级） | 错题知识点建议的"向量 Top-5"实为名称模糊匹配；mastery 数据精度不受影响但录入体验降级 | 合理：模型打包/加载风险后置，P0 流程不阻塞。但意味着计划书 v2.1 上线门"错题录入→mastery 端到端"中的向量环节**尚未真实验证**，建议列为下个迭代最高优先（与 backlog B3 一致） |
| 2 | **OCR 从"关键路径"降级为 501 占位** | v2.2 原计划 OCR 是"关键路径"，实际手动录入保底 | 可接受：与计划书风险登记册"OCR 不达标则转实验功能"预案一致；但需在 v2.2 验收话术上修正，不能宣称 OCR 上线 |
| 3 | **图谱跳过 POC 直接选型 vis-network** | 500 节点性能未经验证（ADR 自设目标 <1s） | 有依据（ADR 对比表完整），但计划书的 C2 压测项因此更重要，建议压测时把图谱初渲染一并纳入 |
| 4 | **自动周复盘定时任务缺失** | 学科级自动周复盘（计划 2.2-4）未见实现，且未列入团队 backlog | 计划书与团队 backlog 的共同盲区，建议补入 backlog |
| 5 | **mastery 调权未接 weight_tuning**（backlog B2） | α₁..α₅ 固定等权 | 与计划排期一致（计划也是 v2.2 接通），属正常延后 |
| 6 | **AICallLog 仅 logging 未持久化**（backlog B1） | 6.5 留痕审计能力降级 | PRD 6.5 明确要求"存储输入依据与理由"，上线前需补齐 |
| 7 | **限流为进程内 dict**（backlog B5） | 重启清零、多进程不共享 | MVP 单进程可接受，部署形态变化时必须处理 |

**总体评价**：团队在 1 天内完成了计划书 16 周排期的主体工程，且对 P0 合规（EgressGuard 默认拒绝、error-parse 重构为引用形态）的实现**优于计划书的最低要求**。偏差集中在"需要真实模型/真实数据/真实内容"的环节（embedding 启用、OCR、内容清单、压测），这些恰恰是计划书标注的依赖外部条件的项，不构成工程质量问题。

---

## 5. 计划书的剩余价值

| 计划书内容 | 现状 | 去向 |
|---|---|---|
| P0 / v2.1 / v2.2 / v2.3 任务分解 | 主体已交付 | **归档**，不再作为执行依据 |
| 出域管控架构（§3.2）、RAG 链路（§3.3） | 已实现且一致 | 归档为设计意图记录（可追溯 EgressGuard 设计来源） |
| 风险登记册（§10） | 8 项中 5 项已被实际决策覆盖 | 保留 3 项仍有效：内容交付延期（D1）、embedding 效果（B3）、OCR 识别率（C4） |
| 验收标准对照（§8 / PRD 12.9） | 未执行 | **仍有效**——建议作为下个迭代验收清单的输入 |
| 立即行动项（§13） | 已过时 | 作废 |

**团队 `module2-backlog.md` 已接管执行层 backlog**（A/B/C/D 四类 + 优先级），计划书不再重复维护。建议在其基础上补 2 项：自动周复盘定时任务（§4 偏差 4）、计划书 §8 验收清单执行。

---

## 6. 后续建议（优先级排序）

1. **启用真实 embedding**（backlog B3）：配置 bge-small-zh 模型 + 切 `kb_embed_mode=local`，验证向量 Top-5 匹配质量——这是板块二算法价值的真实验证点；
2. **执行计划书 §8 验收清单**：出域 CI 断言已有基础（test_egress_ci.py），补压测（C2）与降级链路矩阵；
3. **补自动周复盘定时任务**（§4 偏差 4）：该学科 ≥3 条记录触发，复用现有 knowledge-summary 链路；
4. **内容清单正式交付**（D1）：示例种子 → 数学 50 / 物理 100 / 英语 200 正式内容；
5. **法务两项评审**（D2/D4）：授权文案 v1.5 + 出域边界强化版，卡上线门；
   〔pilot 口径〕团队无法务与外部评审资源，此项不卡任何发布门：授权文案由团队内自行定稿（设计底线），出域边界强化版按「团队内完成 / 记入待办」处理，随板块三启用前自行走查，无外部评审前置。
6. **AICallLog 持久化**（B1）：PRD 6.5 留痕要求，上线前必须。
   〔pilot 口径〕留痕本身属设计底线、需落地；但「上线前必须」不适用 pilot——按「记入待办」档排入 backlog，不阻塞任何试用或发布动作。

---

## 附：文档谱系

```
PRD v1.4 §12
  ├─ module2-3-gap-architecture-api-checklist.md   (2026-08-23, 差距盘点)
  ├─ module2-3-development-plan.md                 (2026-08-23, 16 周计划)
  │    └─ 被团队作为实施蓝本（ADR 显式引用）
  ├─ PR #35 408180b  P0+v2.1+v2.2 实现             (2026-08-24)
  ├─ PR #36 14dc17f  前端补完+v2.3+板块三预留       (2026-08-24)
  │    ├─ adr-vector-embedding.md                  (FAISS + bge-small-zh)
  │    ├─ adr-graph-visualization.md               (vis-network)
  │    ├─ module2-backlog.md                       (执行层 backlog，现行)
  │    ├─ module3-privacy-review.md                (板块三预评审)
  │    └─ module3-statistics-view-design.md        (统计视图层设计)
  └─ module2-3-as-built-vs-plan.md                 (本文档，对照审计)
```

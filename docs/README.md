# docs 文档地图（2026-09-18 整理）

> 新人/新 agent 入口。三栏：**权威文档**（干活依据）、**活跃参考**（有保留价值的在用品）、**已归档**（历史，别据此安排工作）。
> 变更规则：移动/归档任何文档后，必须回本文件同步。

## 一、权威文档（当前生效，干活依据）

| 文档 | 角色 | 备注 |
|---|---|---|
| `openapi.yaml` | **唯一契约真相源**（v1.7.0 · 59 paths · 170 schemas · 表 47 张 / 单 head `b81d83bafb89`） | 改动走 X0 评审 |
| `openapi-usage.md` | 契约使用说明 | 内含历史校验记录，以文首当前口径为准 |
| `product-redesign-target.md` | **产品目标态** v0.29（D1–D59） | 不含 UI 视觉细节 |
| `product-redesign-target.html` | 目标态汇报页 | Skyer 9/17 亲自重做的结构，**只增量编辑，禁止覆盖重建** |
| `refactor-development-plan.md` | 重构主计划（里程碑 M0–M6 / 依赖 / 验收门） | 实施方案四件套 ① |
| `refactor-module-contracts.md` | 板块契约（10 板块所有权 / 协议 / 文件独占表） | 四件套 ②，可当任务单发 |
| `refactor-migration-checklist.md` | 迁移清单（现有页面/接口/表逐项处置） | 四件套 ③ |
| `refactor-decision-mapping.md` | D1–D59 全量映射（零孤儿验收索引） | 四件套 ④ |
| `refactor-implementation-notes.md` | 执行细节（计量/上传/治理/稳定 ID 等） | 与目标态配套 |
| `refactor-2026-09-feature-ia-logic.md` | 现状基线（功能清单/IA/技术债） | 与勘误对照读 |
| `refactor-baseline-recheck-2026-09-18.md` | 现状勘误（10 条已过时 / 7 条仍准确 / 新发现） | 以 HEAD 实测为准 |
| `../PRD-学习状态智能助手.md` | 板块一/二需求基线 + 合规红线 §12 | 新形态以目标态为准（文首有定位说明） |

## 二、活跃参考（在用品，非行动依据）

| 文档 | 角色 | 状态 |
|---|---|---|
| `deployment-stack-evaluation.md` | 部署栈选型 + 落地清单 | P0/P1/P2 多数已完成（文首状态说明）；剩平台选型/密钥/R2 |
| `pending-decisions.md` | #1–#53 决策痕迹 | 已批量拍板，仅支付三项推迟 |
| `module3-consent-copy.md` | 社区授权文案 v1.0（定稿） | 文案资产仍生效，重构 M4 社区接线时复用 |
| `refactor-c-handoff-to-x0.md` | **C → X0 需求单**：`self_report` 软字段可空化 + 记录来源字段（D20/D34/D49 的三处阻塞） | 2026-09-25 新增，**待 X0 评审**；C 侧已按"不造数"口径只做能做的部分 |

## 三、已归档（`archive/` · 历史留痕，勿据此安排工作）

| 文档 | 是什么 | 归档理由 |
|---|---|---|
| `archive/api-design-unified.md` | 早期统一 API 设计（板块一） | 已被 openapi.yaml 取代（母子关系反转） |
| `archive/backend-changes-plan-a.md` | 导学推荐后端改动说明 | 方案 A 已交付，自带头注 |
| `archive/module2-backlog.md` | 板块二剩余 backlog | 未完事项由 X2（QA）接管 |
| `archive/module2-next-iteration-tasks.md` | 板块二下一迭代任务 | 迭代已交付 |
| `archive/module2-refinement-plan.md` | 板块二完善计划 | 迭代已交付 |
| `archive/module2-3-development-plan.md` | 板块二/三开发计划书 | 历史快照，自带头注 |
| `archive/module2-3-gap-architecture-api-checklist.md` | 模块二/三缺口清单 | 缺口已闭合 |
| `archive/module2-3-as-built-vs-plan.md` | 计划 vs 实际交付对照 | 对照基线，事实留痕 |
| `archive/module3-development-plan.md` | 板块三开发计划 | M1–M5 已交付（`d0d3f54`） |
| `archive/module3-m0-decision-proposal.md` + `archive/module3-m0-decisions.html` | 板块三 M0 决策 v1.7 | M0 已关闭 |
| `archive/module3-privacy-review.md` | 板块三隐私预评审纪要 | 评审已完成并落实 |
| `archive/module3-statistics-view-design.md` | 统计视图层设计草案 | 已被实现 |
| `archive/mvp-fix-2026-08-18-postfix.md` | MVP 修复回归报告 | 一次性回归记录 |
| `archive/handoff-ui-redesign-2026-08-18.md` | 「人文风·空气感」UI 重设计交接 | 已被 v0.3 液态玻璃取代，且 UI 未最终拍板（#51） |
| `archive/next-ui-redesign-spec.md` | 下一版 UI 重设计规范 draft | 同上，待新视觉设计文档取代 |
| `archive/feature-placeholder-audit.md` + `archive/feature-placeholder-audit.html` | 空界面/假功能盘点（8-29） | 多项已修复，现状以 `refactor-baseline-recheck-2026-09-18.md` 为准 |
| `archive/adr-graph-visualization.md` | ADR：图谱选 vis-network | 决策仍生效，文档留痕 |
| `archive/adr-vector-embedding.md` | ADR：本地向量库与 embedding 选型 | 决策仍生效（错题本地向量化不出域），文档留痕 |
| `archive/slide-outline.md` | 8-19 对外路演 PPT 大纲 | 一次性产物 |

## 四、其他

- 归档文件内部的相互引用仍为同目录相对路径，移动后未断；活跃文档对归档文件的引用已全部改为 `archive/` 前缀（全量断链检查 0 残留，2026-09-18）。
- `product-redesign-target.html` 与 archive 内的两份 HTML 均为自包含文件（零外部引用），双击可开。

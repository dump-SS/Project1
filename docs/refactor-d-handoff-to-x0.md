# D → X0 契约变更单（知识、题本与 AI 辅导）

> 版本：v1.0 · 2026-09-29 · 提出方：**D 板块**
> 分支：`feat/refactor-knowledge`（基线 `a5d0bbf`）
> 关联：`refactor-module-contracts.md` §2（实体字典）· `refactor-d-knowledge-ref-protocol.md`（知识引用协议，已冻结）
> 状态：**① 题本维度已实现并验证；② 搜题/讲解 paths 待补；③ 两项待拍板**

---

## 0. 本次已落地（有测试，无需 X0 动作）

题本升格 **D48** 的两个正交维度。契约 v1.6.0 里 `ErrorCause` / `ErrorIntent` 枚举与
`kb_errors` 的 `error_cause` / `intent` / `source_exam_id` 三列**本就已就位**，本次只是把
接口层补上（schema + 路由 + 前端服务层），**未新增任何字段名**。

| 改动 | 落点 |
|---|---|
| `ErrorRecord*` 三个 schema 增补三字段（对齐契约已有定义） | `schemas/error_book.py` |
| 录入/更新/列表支持错因与意图，非法枚举 400 不静默丢弃 | `routes/error_book.py` |
| **mastery 只消费「有错因」的错题** | `mastery_engine/__init__.py` |
| 前端题本两维度筛选 + 「复习 / 小测」措辞（不叫组卷） | `pages/Knowledge/`、`services/errorBook.ts` |
| 知识页八合一，**删除 KNOWLEDGE_TREE 硬编码假树** | `pages/Knowledge/index.tsx` |

测试：`tests/test_topic_book.py`（7 例，含 masteries 只吃有错因的对照实验）+ 原有题本 7 例全绿。

---

## 1. 需要 X0 补的 paths（契约登记）

契约 v1.6.0 说明「Explanation / SearchArchive 等 schema **尚未挂到任何 path**，接口由各板块补齐」。
D 侧的实现已按契约字段名写好，请 X0 将下列 paths 补进 `docs/openapi.yaml` 并挂载 router
（`main.py` 挂载也归 X0）。

| Path | 方法 | 用途 | schema |
|---|---|---|---|
| `/search-archives` | POST | 发起搜题（三态），结果归档 | 入：`{subject?, rawText, mode}`；出：`SearchArchive` |
| `/search-archives` | GET | 归档列表（可按 subject / mode 过滤） | `SearchArchive` 列表 |
| `/search-archives/{archiveId}` | GET | 归档详情 | `SearchArchive` |
| `/explanations` | POST | 生成 / 重讲讲解 | 入：`{pointId?, subject, regenerate?}`；出：`Explanation` |
| `/explanations` | GET | 列表（可按 pointId / isCurated 过滤） | `Explanation` 列表 |
| `/explanations/{explanationId}` | GET | 详情 | `Explanation` |

命名一律用**复数资源名 + 复数集合路径**，与既有 `/error-book` 的单数风格不同——
若 X0 要求统一为单数（`/search-archive`、`/explanation`），告知 D 侧改路由前缀即可，无需改实现。

### 1.1 附带登记的 schema 建议

- `KnowledgeRef`：`{pointId, subjectCode, name, mastery?}`，即已冻结的知识引用协议
  （`refactor-d-knowledge-ref-protocol.md`）。F / B / E 三个消费方都在引用它，
  目前只有文档没有契约 schema，建议登记以便契约测试守形。

---

## 2. 待拍板 · 阻塞项（需要你 / 合规拍板，D 侧不自行决定）

### 2.1 ⚠️ 搜题的题面原文能否出域

这是**功能与合规的正面冲突**，D 侧不敢自行决定：

- 事实 A：搜题（解一道具体题）在工程上必须把题面交给模型。
- 事实 B：`egress_guard` 对 `data_class = knowledge_raw` **默认拒绝**；`/error-parse`
  的整改口径是「**错题原文只在本地检索，永不出域**，出域内容仅限 `knowledge_aggregated`
  白名单字段（知识点名称/定义/易错点 + 错因候选）」。
- 事实 C：契约对 `SearchArchive.rawText` 的注释写的是「题面原文属 knowledge_raw：
  本地留存、永不出域」。

若严格按 B/C 执行，**「直给（direct）」这一态无法真正解出具体题目**，只能给出该知识点的
通用解法与思路。三个可选口径，请拍一个：

| 方案 | 含义 | 代价 |
|---|---|---|
| **A · 严守不出域** | 搜题只发聚合字段，模型给「这类题怎么解」的方法讲解，不接具体数值 | direct 态名不副实，产品体验打折 |
| **B · 用户即时输入豁免** | 用户当场输入/拍照的题目视为「主动查询」，不属于已入库的 knowledge_raw，允许出域 | 需要在 egress_guard 里新增一类 data_class 并说明依据 |
| **C · 本地模型兜底** | 解题走本地/私有化模型，不出域 | 取决于是否有可用本地模型，成本与质量待评 |

**当前实现已按 A 保守处理**（不发送题面原文），等拍板后再切。

### 2.2 难度双层（D13）的个人覆写字段

目标态 §4.4 的「难度双层 = 官方基线 + 个人覆写（本账号内免审核即时生效）+ 众包信号」，
其中**个人覆写需要落库**，契约与 `kb_points`（全局表）目前都没有「按用户覆写」的位置。
建议方案（请 X0 选或另提）：

- 方案 1：新增 `kb_point_difficulty_overrides`（user_id + point_id 唯一，difficulty 1–5）
- 方案 2：并入 `user_profiles`（B 板块画像表，加一条 `difficulty_override` 键）

⚠️ 目标态同时提醒：难度覆写若用于聚合属「学生水平」敏感数据，需**匿名 + 最小群体**。
当前知识页只展示官方基线（`difficulty`），个人覆写 UI 留白待字段落地。

---

## 3. 需要知晓的行为变更（会影响其他板块）

**mastery 与薄弱归因不再消费「无错因」的错题**（D48 硬要求）。连带影响：

- `compute_weakness_hints` / 图谱 `weakPointIds` / `POST /plans` 的 `weaknessHints`
  **都只认有 `error_cause` 的错题**。
- ⚠️ **存量导入的错题若没有 `error_cause`，会整体退出掌握度计算**（样本归零、薄弱点变空）。
  pilot 删档期可接受；若存量数据要保留，需先批量补错因，否则 C 板块的短板提示会「凭空失灵」。
- 已同步修改 `tests/test_weakness_hints.py` 的 fixture（造错题现在必须带错因），
  **请 C / X2 注意这条口径**，不要以为是 bug。

---

## 4. 给 X0 的评审要点

- [ ] 上表 6 个 paths 是否照此登记（命名是否要改单数）
- [ ] `KnowledgeRef` 是否登记为契约 schema
- [ ] 2.1 搜题出域口径拍 A / B / C 哪一个
- [ ] 2.2 个人难度覆写落库选方案 1 还是 2
- [ ] 迁移是否仍为**单 head**（D 侧未新增任何表，未写迁移）

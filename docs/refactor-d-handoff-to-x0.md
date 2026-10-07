# D → X0 契约变更单（知识、题本与 AI 辅导）

> 版本：v2.0 · 2026-09-30 · 提出方：**D 板块**
> 分支：`feat/refactor-knowledge`（基线 `fcccb08`，已 rebase 到最新 main）
> 契约基线：**v1.7.1**（64 paths / 174 schemas / 单 head `c7a1f2e4d9b3`）
> 关联：`refactor-module-contracts.md` §2（实体字典）· `refactor-d-knowledge-ref-protocol.md`（知识引用协议，已冻结）
> 状态：**① 题本维度已实现；② 搜题/讲解已实现，paths 待登记；③ 两项拍板已落，只剩契约登记类动作**

> v1.0 → v2.0 变更：按 X0/研发管理 2026-09-30 评审意见修订——
> 契约版本订正为 v1.7.1；§2.1 出域口径已拍板（新增 `user_error_content`）并已实现；
> §2.2 难度覆写定为**方案 1**；新增 §2.3（错因是否必填的确认）。

---

## 0. 本次已落地（有测试，无需 X0 动作）

题本升格 **D48** 的两个正交维度。契约 v1.7.1 里 `ErrorCause` / `ErrorIntent` 枚举与
`kb_errors` 的 `error_cause` / `intent` / `source_exam_id` 三列**本就已就位**，本次只是把
接口层补上（schema + 路由 + 前端服务层），**未新增任何字段名**。

| 改动 | 落点 |
|---|---|
| `ErrorRecord*` 三个 schema 增补三字段（对齐契约已有定义） | `schemas/error_book.py` |
| 录入/更新/列表支持错因与意图，非法枚举 400 不静默丢弃 | `routes/error_book.py` |
| **mastery 只消费「有错因」的错题** | `mastery_engine/__init__.py` |
| 前端题本两维度筛选 + 「复习 / 小测」措辞（不叫组卷） | `pages/Knowledge/`、`services/errorBook.ts` |
| 知识页八合一，**删除 KNOWLEDGE_TREE 硬编码假树** | `pages/Knowledge/index.tsx` |

测试：`tests/test_topic_book.py`（7 例，含 mastery 只吃有错因的对照实验）+ 原有题本 7 例全绿。

---

## 1. 需要 X0 补的 paths（契约登记）

D 侧实现已按下列 paths 写好并挂上 router（`main.py` 挂载也请 X0 复核命名）。
**复数资源名已获评审确认**（`/search-archives`、`/explanations`），
不为了迁就旧的单数风格（`/error-book`）去改新资源。

| Path | 方法 | 用途 | schema |
|---|---|---|---|
| `/search-archives` | POST | 发起搜题（三态），结果归档 | 入：`{subject?, rawText, mode}`；出：`SearchArchive` |
| `/search-archives` | GET | 归档列表（可按 subject / mode 过滤） | `SearchArchive` 列表 |
| `/search-archives/{archiveId}` | GET | 归档详情 | `SearchArchive` |
| `/explanations` | POST | 生成 / 取回讲解（两态） | 入：`{pointId?, subject, mode}`；出：`Explanation` |
| `/explanations` | GET | 列表（可按 pointId / isCurated 过滤） | `Explanation` 列表 |
| `/explanations/{explanationId}` | GET | 详情 | `Explanation` |

语义说明（评审已确认「复数路径 OK，旧的单数路径不要动」）：

- `POST /explanations` 的 `mode=original` 是**取回**（200，不调模型），
  `mode=regenerated` 是**新建**（201）。同一个 POST 两种状态码是刻意的：
  「回顾上次讲法」不该被当成创建资源。

### 1.1 `KnowledgeRef` 登记（已同意）

`{pointId, subjectCode, name, mastery?}`，即已冻结的知识引用协议
（`refactor-d-knowledge-ref-protocol.md`）。F / B / E 三个消费方都在引用它。
评审结论：**四字段照此登记，消费方不得自行扩展字段**。

### 1.2 ⚠️ 两处需要一并登记的契约增量（v1.0 未提，实现时才发现）

| 位置 | 现状 | 需要改成 | 为什么 |
|---|---|---|---|
| `SearchArchive.pointIds` | `array` / `items: string` | `items: $ref KnowledgeRef` | D24 要求三态结尾都输出知识点卡片，卡片必须带 `mastery`；纯 id 数组撑不起这张卡，前端还得再查一次 |
| `SearchArchive` | 只有 `solution: string` | 增 `solutions: array`（≤3）与 `solutionCount: int` | D52 要求「多解分页 ≤3，默认只给主解」；`solution` 仍保留为主解正文，向后兼容 |

两处都是**加信息不减信息**：`solution` 字段没动，老消费方不受影响；
`pointIds` 从 string 数组升级为对象数组属于破坏性变更，请 X0 一并同步 F / B / E。

### 1.3 ⚠️ 契约正文三处「永不出域」表述已过时，需按新口径改写

§2.1 拍板后，**用户自己的内容不再归 `knowledge_raw`**。契约里这三处仍写着旧口径，
不改写的话 X0 / X2 / 后续接手的人会继续按「永不」执行，与实现直接打架：

| 位置 | 现文 | 建议改写 |
|---|---|---|
| L6228 / L6236 `SearchArchive` | 「题面原文属 knowledge_raw：**本地留存、永不出域**」 | 题面属 `user_error_content`：本地留存；**仅在用户当场发起时**可随一次授权出域，禁止后台批量；embedding 仍走本地模型 |
| L72–73 tags「错题本」 | 「错题原文/作答/正确答案/自述错因属 knowledge_raw，按 PRD 12.6 禁止出域」 | 属 `user_error_content`（用户自己的内容）：默认不出域，**用户在错题本点「讲一遍 / 出变式 / 相似题」时按单次授权放行**；系统批量导出 / 定时任务禁止 |
| L2452–2454 `POST /error-book` | 「永不进入出域 payload（EgressGuard knowledge_raw 拒绝序列化）」 | 录入**不**出域（这条不变）；用户后续主动发起讲解 / 变式时按 `user_error_content` 单次授权 |

⚠️ 注意区分两条链，别混（PRD 12.6）：
`knowledge_raw` 仍**绝对禁止**——它专指爬取的教材 / 题库素材（版权与第三方数据）；
知识库向量走智谱 API 是**另一条链**（`EMBED_SRC_KB`），与用户内容的本地 embedding
（`EMBED_SRC_USER`，强制本地）互不干涉。

---

## 2. 已拍板事项（v1.0 的「待拍板」已全部关闭）

### 2.1 ✅ 搜题题面出域：**新增 `user_error_content` 数据类**（不是 A / B / C 里的任何一个）

拍板结论是**分类纠错**，不是在原三方案里挑一个：

- 原先把用户自己录入的错题一并归进 `knowledge_raw`，**是分类错了**——
  `knowledge_raw` 本是给爬取的教材 / 题库素材用的（版权与第三方数据问题，永不出域合理），
  用户自己的内容不该与它同等对待。
- 判定规则：**不看「存没存过」，看「这次是不是用户主动发起 + 内容是不是用户自己的」**
  - 用户在对话里当场输入 / 拍照搜题 ✅ 允许
  - 用户在错题本点「讲一遍 / 出变式 / 相似题」 ✅ 允许（用户主动 + 自己的内容）
  - 系统自动批量外发（后台生成、定时推送等） ❌ 禁止（无用户即时意图）
  - 知识点库原始素材 ❌ 永不出域（**不变**）
  - embedding ❌ 必须本地模型（**不变**）

四道加固（放宽红线的前提，已逐条落地 + 测试）：

| # | 加固 | 落地 | 测试 |
|---|---|---|---|
| ① | 每次点击即一次授权，禁后台任务 / 预生成 | 只有 `POST /search-archives` 触发，同步生成 | `test_search_egress.py::test_search_route_has_no_background_path`（AST 扫源码） |
| ② | 优先境内服务商、不留存不训练 | 沿用 `llm_provider` 的 `llm_base_url`，不引入第二家 | —（配置层） |
| ③ | 用户可关闭 | `settings.knowledge_ai_egress_enabled`（**已存在**，默认 False），关闭退回本地检索 + 通用讲解 | `test_egress_off_sends_no_raw_text` |
| ④ | 出域留痕（用户 / 内容类型 / 时间） | 新增 `egress_log.py`，独立 `egress` logger | `test_egress_on_sends_raw_text_and_logs` |

另外保留「能走聚合就走聚合」：只有 `direct` 态（要真解出这道题）才需要题面；
`analytic` / `guided` 先走 `knowledge_aggregated`，不因为开了口子就一律发原文
（`test_only_direct_mode_needs_raw_text`）。

**文首「当前实现已按 A 保守处理」的说法作废**，实现已切到新口径。

### 2.2 ✅ 难度双层（D13）个人覆写：**方案 1 — 独立表**

新建 `kb_point_difficulty_overrides`（`user_id + point_id` 唯一索引，`difficulty` 1–5），
**不并入 `user_profiles`**。理由（评审给出）：`user_profiles` 是 B 板块的画像表，
写入是模型隐式推断；难度覆写是**用户显式设置**，两者语义不同，混在一张表里
后面分不清「这是用户自己设的」还是「模型猜的」。

- 迁移仍归 X0（D 侧未写任何迁移，单 head 不变）。
- 知识页当前仍只展示官方基线（`kb_points.difficulty`），个人覆写 UI 留白待字段落地。
- ⚠️ 目标态提醒：难度覆写若用于聚合属「学生水平」敏感数据，需**匿名 + 最小群体**。

### 2.3 ✅ 录入时错因**不是必填**（确认答问）

> X0 问：「请确认：录入时错因是不是必填？如果不是，建议补引导提示
> 「填上错因，这条才会计入掌握度和薄弱点」。不补的话用户会以为是 bug。」

**确认：错因不是必填，且不应改成必填。**

- `ErrorRecordCreate.errorCause` 可空，`_validate_dimensions` 只拒绝**非法取值**，
  不拒绝缺失——这是 D48 的刻意设计：只填意图的条目是 **star 题**
  （「我觉得这题好」），照样要能收进来、照样进艾宾浩斯复习队列，
  只是不喂掌握度。一刀切必填会把 star 题这条路径堵死。
- 但评审指出的体验风险成立，已补引导文案，摆在题本区最显眼处：

  > 错因不必填，但**填上错因，这条才会计入掌握度和薄弱点**；只填意图的是 star 题，照样进复习队列。

  落点：`frontend/src/pages/Knowledge/index.tsx`（题本 section header 下）。
  之所以写「不必填」而不写「请填写」：前者如实告知规则，后者像报错。

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

- [ ] 上表 6 个 paths 是否照此登记（命名维持复数）
- [ ] `KnowledgeRef` 是否登记为契约 schema（四字段，消费方不得扩展）
- [ ] §1.2 两处增量：`pointIds` items 改 `KnowledgeRef`（**破坏性**，需同步 F/B/E）、
      增 `solutions` / `solutionCount`
- [ ] **§1.3 契约正文三处「永不出域」改写**（`SearchArchive` L6228/L6236、
      tags 错题本 L72–73、`POST /error-book` L2452–2454）——不改会与实现打架
- [ ] §2.2 `kb_point_difficulty_overrides` 迁移（唯一索引 `(user_id, point_id)`，难度 1–5）
- [ ] 迁移是否仍为**单 head**（D 侧未新增任何表，未写迁移）
- [ ] 精品样例种子 `scripts/seed_curated_explanations.py`（5 条）是否并入 X0 的种子流水线
      ——当前挂在 `u_curated` 系统账号下，幂等 upsert

---

## 5. ⚠️ 跨板块触碰说明（出域调用点全仓审计附带修复，需 E / X2 / X0 知悉）

做「加固 ① 有没有后台路径偷偷出域」的审计时，用 AST 全仓扫了所有
`*.generate(...)` 调用点，发现**两处声明缺失**。修复**不改变任何行为**，
只是把本该声明的出域类别补上：

| 文件 | 归属 | 问题 | 处置 |
|---|---|---|---|
| `routes/knowledge.py` `error-parse` | **D**（本人） | 注释写着「由 EgressGuard 白名单强校验」，但 context 里既无 `data_class` 也无 `egress_fields`——`_build_error_parse_prompt` 算出的 `egress` **被丢弃了**。`_enforce_egress` 对 `data_class=None` 直接放行，**整改后的校验从未真正执行** | 补 `egress_fields` + `data_class=knowledge_aggregated` |
| `daily_summary.py:186` | **E** | 同样未声明 | 补 `data_class=state_plan` + `scene` |

**内容上没有发生泄漏**：error-parse 的 prompt 只含知识点名/定义/易错点，
daily_summary 只含结构化统计（时长/学科/完成情况/自评均值/情绪计数，note 不入 prompt，
PRD 6.2）。**坏的是机制不是内容**——机制不生效，以后谁改了 prompt 加上原文，
没有任何东西会拦。

### 配套守护（落在 `tests/test_egress_ci.py`，属 X2，请 X2 复核）

1. **静态**：扫全仓 `generate` 调用点，**漏声明 data_class 直接挂 CI**；
   声明了但取值拼错同样挂。动态取值必须显式登记在 `_DYNAMIC_DECLARE_OK`
   并写明理由，且有断言防止豁免项失效后留在表里。
2. **运行时**：`test_error_parse_really_goes_through_guard` 从 provider 侧断言
   error-parse 真的传了 `data_class` 与 `egress_fields`——
   静态只能证明「写了字面量」，这条证明「真的传到了」。
   已验证有效性：**临时把修复回退，两条测试都报红**。
3. **定时任务**：`jobs/` 下的 LLM 调用只允许 `knowledge_aggregated`
   （定时无用户即时意图，**永远**不该出现 `user_error_content`）。

### 给 X0 的建议（未擅自改，属 X0/G 的文件）

`llm_provider._enforce_egress` 对 `data_class=None` **默认放行**（向后兼容板块一）。
而 `Guard.check` 对未声明是**拒绝**的——同一件事两道闸标准相反。
现在全仓 9 个调用点已全部显式声明，**可以安全收紧为默认拒绝**；
收紧后新增调用点漏声明会立刻报错，而不是静默出域。
是否收紧请 X0 定（会动 `llm_provider.py`，G 板块登记文件）。

---

## 6. 测试

`backend/tests/test_search_egress.py`（22 例）覆盖：

- 出域红线：`knowledge_raw` 仍被拒；`user_error_content` 有自己的白名单；
  用户内容 embedding 仍禁止出域
- 开关：关闭 → prompt 里**不得出现题面**；开启 → 放行并留痕；无设置行 = 关闭
- 「能走聚合就走聚合」：只有 direct 态需要题面
- 加固 ①：AST 扫源码，路由不得出现后台 / 定时入口
- D24：三态被记忆、非法 mode 400、知识点卡是冻结的四字段协议（mastery 为 null 不是 0）
- D52：两态并存不互顶、中学解法约束进 prompt、查词卡只给语言类学科、
  精品样例与动态生成可区分、种子 3–5 条

全量：`407 passed / 5 skipped`；前端 `tsc --noEmit` 0 错误。

# 错题本 v2 · 需求文档（v2.0 终稿）

> 文档编号：RDD-ERRBOOK-002　｜　状态：定稿　｜　契约：`docs/openapi.yaml v1.28.0`
> 本文档只描述“要做什么”，不保留演进过程；所有结论均已定稿。

## 0. 速览

**一句话**：一本会自己整理的错题本——三秒收进来，按“今天该看什么”排好，一次只看该看的那几道；跨章大题按章节拆开，每一处就地可读。

| 项 | 内容 |
|---|---|
| 范围 | 录入 / 组织 / 查看 / 排序 / 章节视图 / 复习 / 对话接入 |
| 不做 | 组卷与出题、错题原文出域、标签参与掌握度、跨学科标签池、收藏转错题与拍照录入（P2） |
| 指标 | 录入 3 秒内完成｜列表 P95 ≤300ms（≤2000 行）｜复习首题 ≤200ms｜零新增出域 |
| 落点 | `pages/ErrorBook/`、`services/errorBook.ts`、`routes/error_book.py`、`schemas/error_book.py`、`models/knowledge.py`、`tests/test_error_book.py` |

**四条不变量**（任何改动不得违反）：

1. 错题原文永不出域（`EgressGuard.knowledge_raw`）；
2. 错因非必填（star 题路径不得被堵死）；
3. 排序分不进界面，界面只有分级一把星尺；
4. 分页、幂等、批量写的语义在任何视图下保持一致。

## 1. 设计原则

| # | 原则 | 落点 |
|---|---|---|
| 1 | 录入只管“别丢”，整理才管“能用” | 两段式录入 + 待整理收件箱 |
| 2 | 人对分组的理解强于对分数的理解 | 分组主视图，排序分只驱动顺序 |
| 3 | 它是笔记本，不是体检报告 | 纸张批注色、不催促的文案 |
| 4 | 默认路径不出现需要用户做的选择 | 3 秒录入、只露两种排序、无权重 UI |
| 5 | 一道题的知识位置是区间，不是点 | 跨度模型 + 章节多出现 |

## 2. 用户旅程

| 时刻 | 发生什么 |
|---|---|
| 刚考完 | 贴一句题面就存下，标「待整理」 |
| 晚上有空 | 收件箱一屏一条，补错因 / 标签 / 分级；或标成「好题」 |
| 对话里讲到 | 点「记入错题本」直接入库；或「整理这轮对话」出候选 |
| 第二天打开 | 顶栏三个数，下面按分组排好 |
| 想知道缘由 | 点卡片看「为什么排在这」 |
| 顺教材过一遍 | 切章节视图，跨章题在多章各出现一次，副卡就地展开 |
| 坐下来复习 | 全屏流：一次一题、翻面、会 / 不会 |
| 搞定了 | 点已解决，淡出归档；再错会冒回来 |

## 3. 信息架构与布局

### 3.1 四层结构

| 层 | 左 | 右 |
|---|---|---|
| 1 顶栏 | 状态数字：`今天 N 道到期 · 待整理 M` | 视图簇：`分组视图 / 章节视图` + `按题去重` |
| 2 学科 Tab | 有数据的 + 最近使用 | 「更多」收起其余 |
| 3 操作行 | `筛选` / `排序` | 计数：分组 `N 道`｜章节 `N 道 · M 处` |
| 4 列表 | — | — |

### 3.2 布局规则

1. **数字不随视图移动**：`今天 N 道到期` 是 due 数，全页唯一，切视图、切排序都不动。
2. **视图簇聚合**：视图切换与「按题去重」都在回答“怎么读列表”，因此同处顶栏右侧；「按题去重」不得被放进操作行当筛选器。
3. **操作行是“对列表做什么”**：筛选、排序在左；计数跟随列表在右。
4. **计数格式随视图变**：分组视图 `N 道`；章节视图 `N 道 · M 处`。
5. **隐藏不塌陷**：`按题去重` 在分组视图不可见，但保留占位，避免视图切换按钮横向跳动。
6. **待整理为 0 时整段隐藏**，连同前面的分隔点一起消失。
7. **弹层锚定**：筛选 / 排序弹层按按钮左边缘对齐，向下展开、浮于列表之上，不推挤布局。

### 3.3 学科 Tab

- 只显示「有数据的 + 最近使用的」学科，其余收进「更多」（全部学科可达）。
- 新用户默认学科 = 最近一条学习记录的学科；无记录则数学。

## 4. 功能需求

### 4.1 录入

**FR-01 两段式录入 + 幂等**

- 第一段只填题面（≤4000 字）+ 学科（默认上次），提交即入库：`stage=raw`、`status=open`、`source=manual`。
- 两道幂等防线：

| 防线 | 触发 | 行为 |
|---|---|---|
| 指纹 | 无 `Idempotency-Key`，60 秒内同用户、同学科、`rawText` 完全相同 | 返回原记录 + `X-Deduplicated: 1` |
| 幂等键 | 请求头 `Idempotency-Key` | 见 §7.3 |

- `?force=true` 只跳过指纹，不跳过幂等键。
- 状态码恒 201，区分靠响应头。

**FR-02 待整理收件箱**

- 只露错因 / 标签 / 分级，可勾「主考点」；显示「跨 3 章 · 将拆为 3 处」。
- 必须表态，但不是必须填错因：选一个错因，或选「好题 / 存疑」→ 隐式写 `intent`、`errorCause=null`。
- `stage` 变更条件：完成上述任一表态即置 `organized`；只填标签或分级不算表态。
- 「意图」「star 题」这些词不出现在界面。

**FR-03 对话内明示录入**：消息操作区「记入错题本」→ 预填浮层 → 确认即入库（`chat_mark` + `sourceRef`），不二次确认。

**FR-04 推断候选**：默认手动「整理这轮对话」；候选必须引用原话；30 天 TTL；只在对话页出现；接受用条件更新保证幂等。

### 4.2 组织

**FR-05 标签**

- 学科独立池；≤8 个/题、≤16 字/个；输入即联想 + 最近使用置顶；支持重命名 / 合并；不参与 mastery。
- 敏感词覆盖：`rawText`、`errorNote`、每个 `tag`、occurrence 的 `focus` 与 `note`、`tags/rename` 的目标名。
- 预置标签白名单跳过检测；命中 400 并指明字段。

**FR-06 分级**

- 1–5 整数星；三档人话：一定要会（4–5）/ 差不多（3）/ 有印象（1–2）。
- 智能评级按“重要程度 × 掌握情况”中和（见 A1）；手改后 `severitySource=user`，永不被自动覆盖；可「恢复智能评级」。
- 重算触发点：仅 ①新建 ②主考点变更 时重算，且仅当 `auto`。复习不触发重算——否则星级会随复习跳动，破坏“绝对判断”语义。

### 4.3 查看

**FR-07 筛选**

- 三态：全部 / 还没搞定（open 且 `errorCause` 非空）/ 已经搞定。
- 错因多选：`?errorCause=a&errorCause=b`；空 = 不筛；非法值 400；单值调用行为不变。
- 标签、分级、搜索词与以上为「且」；`intent` 仅 API 可用，界面不暴露。
- 默认收起。

**FR-07b** `stage=raw` 的题不进主视图、不进分组、不进复习队列，只在收件箱。

**FR-08 排序与分组**

`is_split` = `distinct_chapters ≥ 3` 或 `span_p ≥ 0.15`。

| 序 | 分组 | 判定（自上而下，命中即止，用 `p_smart`） |
|---|---|---|
| 1 | 已归档 | `status=resolved` |
| 2 | 今天复习 | 逾期 ≥3 天 且 open |
| 3 | 正在学 | `not is_split` 且 `\|p_smart − p_anchor\| ≤ 0.15` 且 `last_active` 30 天内 |
| 4 | 综合应用 | `is_split` 且 open |
| 5 | 基础补漏 | `not is_split` 且 `p_smart ≤ 0.30` 且 `last_active` 早于 60 天前 |
| 6 | 其他 | 其余 |

`last_active = max(created_at, last_reviewed_at)`。无轴学科：无「综合应用」「基础补漏」，「正在学」→「最近动过」。

三个位置量：

| 名称 | 非拆解 | 拆解 | 用途 |
|---|---|---|---|
| `p_smart` | 加权 | `pMax` | 排序、分组、bucket |
| `p_dedupe` | `p_key` 所属章 | `pMin` | 章节视图按题去重 |
| `p_occ` | `p_key` 所属章 | 该处自身 `p` | 展开的每一处 |

排序选项按轴显隐：`chapter_seq`/`topological` → 「章节顺序」；`module_seq` → 「模块顺序（仅粗略参考）」；`none` → 无顺序项。主界面只露「智能 / 最近录入」，其余在「高级」。

**FR-12 首屏**：见 §3。补充：`counts` 只随学科变，不随筛选变；切筛选不重新计算数字。

**FR-13 卡片：讲解 + 复盘**

- 列表卡片只有一个主动作（点击展开）；展开后「讲解」内含两个 tab：

| tab | 接口 | 入参 |
|---|---|---|
| 解析 | `POST /error-parse` | 仅 `{ errorId }` |
| 复盘 | `POST /knowledge-summary` | 真实统计 + `mastery_changes`（来自 `/mastery`）+ `state_context`（状态源） |

- 复盘数据源强制：`dataSufficient=false` 时文案为「数据不足，先积累 3 次记录」，禁止编数；取不到就留空；前端禁止任何常量。
- 解析降级：响应 `degraded=true` → 前端标「离线解析」。
- 缓存：按 `errorKey + pointsHash` 缓存 1 小时。
- 「去复习」；「⋯」＝编辑 / 标记已解决 / 删除。

**FR-14 章节视图**（`sort=chapter` 且轴 ≠ none）

| 角色 | 形态 | 交互 |
|---|---|---|
| 主卡（最早章） | 完整卡 | 「本题另见」列出其它出现位置，点击才定位；定位到副卡时同时展开 |
| 副卡（其余章） | 折叠行 `[此题 2/3] 题面摘要 · 侧重点 · 展开` | 就地展开，不滚动、不跳回主卡 |

- 副卡与主卡同权，状态互不影响；展开态键 = `errorId + '#' + occurrence.key`。
- 副卡头部可在各侧重点之间互跳。
- 分页按「处」计；「按题去重」用 `p_dedupe` 且无副卡。
- `occurrences` 为空：轴 = none → 不出现章节视图；轴存在但无 seq → 一条 `isUnlocated` 占位。

**FR-15 考查概括**：有轴按 `p` 升序；无轴按 `exam_weight` 降序再 `point_id`；最多 3 个，超出「等 N 项」；拆解题加「（N 章）」；同章多点侧重点写「等 N 点」。

**FR-16 批量侧重点**：一屏 N 行；只提交改动行；单处清空走 `PATCH focus=null` 或 `DELETE`。

**FR-17 复习历史**：列表只带 `reviewCount` / `lastRecall`；详情 `GET /{id}/reviews?limit=20`（上限 50）；卡片展开区显示「复习 4 次 · 记住 3 次」+ 最近 5 条。

**FR-18 来源考试**：详情下拉可改选 / 清除；列表不显示；考试已删 → 显示「已删除的考试」并可清除。

**FR-19 未定位兜底**：「未定位」行可点击进编辑（`PATCH pointIds`）；收件箱保存后 toast 附「去关联知识点」。

### 4.4 复习

**FR-09 全屏复习流**：`/error-book/review`；一次一题、翻面看错解 / 正解、会 / 不会、进度条、可退出、结束页统计。

| 入口 | 组队 |
|---|---|
| 「复习今天 N 道」 | N＝due 数；「一定要会」替换队尾不追加，总数恒 ≤ N |
| 「加练 N 道」 | 上限 12：必看(≤4) → due → current → base → 有印象补位 |

`due=0` → 主按钮「加练一组」。

**FR-10 已解决**：淡出折叠进「已归档」（约 300ms）+ 说明文案；可重新打开。

**FR-11 编辑 / 删除**：`PATCH` 全字段；删除为软删 + 二次确认。

## 5. 数据模型

| 表 | 变更 |
|---|---|
| `kb_errors` | +`severity`(1–5)、`severity_source`、`source`、`source_ref`、`stage` |
| `kb_error_points` | +`is_primary` |
| `kb_error_tags` | 新增：`error_id` + `subject` + `tag`(32)；`Unique(error_id, tag)` |
| `kb_error_candidates` | 新增：推断候选，30 天 TTL |
| `kb_error_occurrences` | 新增：仅存覆写，`error_id + axis_seq` 唯一 |
| `kb_idempotency` | 新增：`user_id + key` 唯一 + `body_hash`，保留 24 小时 |

## 6. 算法

### 6.1 RANK_CONFIG

```python
RANK_CONFIG = {
  "version": 3,
  "weights":      {"order": 1.5, "importance": 1.5, "recency": 1.0},
  "recency_days": 60, "due_days": 3, "due_boost": 0.15,
  "span_split": 0.15, "span_break": 0.30, "span_floor": 0.25,
  "info_full": 16,
  "beta": {"base": 0.60, "span": 0.20, "min": 0.50, "max": 0.75},
  "progress_eps": 0.05, "current_band": 0.15, "base_p": 0.30,
  "top_primary": 4, "batch_size": 12, "scan_cap": 2000,
}
```

### 6.2 A1 智能分级

```
点集 = is_primary 存在 ? [is_primary 点] : 全部关联点
importance  = 0.7×exam_weight + 0.3×(frequency−1)/4
mastery_gap = sample_size ≥ 3 ? (1−mastery) : 0.6
repeat      = min(1, 同知识点未解决错题数/3)
severity = clamp(round(1 + 4×(0.45×mastery_gap + 0.40×importance + 0.15×repeat)), 1, 5)
```

### 6.3 A2 位置量

```
p_i = percentile_rank(seq)；pMin, pMax, span_p = pMax − pMin
is_split = (distinct_chapters ≥ 3) or (span_p ≥ span_split)

p_key 阶梯：① is_primary ② max(exam_weight×difficulty)，同分 point_id 字典序
           ③ max(confidence) ④ point_id 字典序
β = 0.60 if (w_key + w_last) == 0 else clamp(0.60 + 0.20×(w_last−w_key)/den, 0.50, 0.75)

p_smart  = is_split ? pMax : (1−β)p_key + β·p_last
p_dedupe = is_split ? pMin : p_key
p_occ    = is_split ? 该处 p : p_key
```

无知识点的题：`p = 0.5`，`is_split = false`，`unlocated = true`。

### 6.4 A3 顺序轴

| 优先级 | 策略 | 条件 |
|---|---|---|
| 1 | `topological` | 参与 prerequisite 图的知识点 ≥60% |
| 2 | `chapter_seq` | 数学 / 物理 / 化学 / 生物 |
| 3 | `module_seq` | 语文 / 英语 / 历史 / 地理 / 政治 |
| 4 | `none` | 其余 |

`levels` = 有效 order 值去重档数；`levels < 2 → I_sub = 0`（短路，不进 `log2`）。拓扑未覆盖的点视为无 `seq`。

### 6.5 A4 排序分

```
I_sub  = 0 if levels < 2 else clamp(log2(levels)/log2(16), 0, 1)
I_item = I_sub × clamp(1 − span_p/span_break, span_floor, 1)

order  = (axis == none) ? 0
       : chapter  ? 1 − p_smart
       : progress ? 1 − |p_smart − p_anchor| / max(p_anchor, 1−p_anchor, progress_eps)

w_o' = w_o × I_item
w_i' = w_i + (1−I_item) × w_o × w_i / (w_i + w_r)
w_r' = w_r + (1−I_item) × w_o × w_r / (w_i + w_r)
raw  = (w_o'·order + w_i'·importance + w_r'·recency) / (w_o + w_i + w_r)
rank = clamp(1 + 4×(raw + dueBoost), 1, 5)
```

折扣曲线（N=30 示例）：1 章 1.00｜2 章 0.89｜3 章 0.77｜4 章 0.66｜5 章 0.54｜6 章 0.43｜7 章 0.31｜≥8 章 0.25（触底）。

有效占比：

| 场景 | I_item | 顺序 / 考频 / 时间 |
|---|---|---|
| 理科单章 | 1.000 | 37.5 / 37.5 / 25.0 |
| 理科跨 3 章 | 0.770 | 28.9 / 42.7 / 28.4 |
| 理科跨 8 章 | 0.250 | 9.4 / 54.4 / 36.3 |
| 文科单章（3 档） | 0.396 | 14.9 / 51.1 / 34.0 |
| 文科单章（9 档） | 0.792 | 29.7 / 42.2 / 28.1 |
| 文科跨模块 | 0.099 | 3.7 / 57.8 / 38.5 |
| 无轴 | 0 | 0 / 60 / 40 |

### 6.6 A5 进度锚点

`anchorMode=auto（默认）|manual`；优先级 `user_set > 推断 > 回退 chapter`。手设 `anchorSeq` 换算 `p_anchor`；推断＝最近 30 天 `p_i` 中位数，样本 <3 不可用；`manual` 未设时显式引导，绝不偷用推断。

### 6.7 A6 解释层

```
primary = is_split ? "跨 {n} 章 · 综合" : argmax(contribution)
contribution_i = w_i'·f_i / Σ(w'·f)
```

`Σw·f = 0` → 「暂无足够信息排序」，不输出 0%。无轴时只渲染两条贡献行。

### 6.8 A7 occurrences

```
轴 = none            → []
轴存在、有点          → distinct(axis_seq) 按 p 升序；focus 取该章 exam_weight 最高点名（同章 ≥2 点加「等 N 点」）
轴存在、全部点无 seq  → 单条 { axisSeq:null, chapterLabel:"未定位", isUnlocated:true, p:0.5 }
覆写优先；孤儿忽略
```

## 7. 接口

### 7.1 端点

| 接口 | 说明 |
|---|---|
| `GET /error-book` | `stage` `scope` `errorCause[]` `tag[]` `tagMode` `severity` `sort` `textbookMode` `anchorSeq` `w*` `explain` `debug` `explode` `page` `pageSize` |
| `POST /error-book` | 创建；`?force=`；`Idempotency-Key` |
| `GET / PATCH / DELETE /error-book/{id}` | 详情 / 编辑 / 软删 |
| `POST /error-book/{id}/review` | 提交复习结果 |
| `GET /error-book/{id}/reviews` | 复习历史（含归属校验） |
| `POST /error-book/{id}/severity/suggest` | 重算分级（`force` 才覆盖 user） |
| `PUT /error-book/{id}/occurrences` | 批量 upsert；只提交改动项；不删行 |
| `PATCH / DELETE /error-book/{id}/occurrences/{axisSeq}` | 改 / 删单处覆写 |
| `GET /error-book/tags` ｜ `POST /error-book/tags/rename` | 词表 ｜ 重命名合并 |
| `GET /error-book/review-batch?mode=today\|extra` | 复习队列 |
| `.../candidates` + `accept` / `ignore` | 推断候选 |
| `POST /error-parse` ｜ `POST /knowledge-summary` | 讲解 ｜ 复盘 |

### 7.2 `ErrorRecord` 字段

`errorId`、`subject`、`rawText`、`studentAnswer`、`correctAnswer`、`errorType`、`errorNote`、`status`、`errorCause`、`intent`、`sourceExamId`、`source`、`sourceRef`、`stage`、`severity`、`severitySource`、`severityReason`、`tags[]`、`points[]`（含 `isPrimary`）、`occurrences[]`、`isSplit`、`bucket`、`examSummary`、`reviewCount`、`lastRecall`、`createdAt`、`lastReviewedAt`、`nextReviewAt`。

`ErrorOccurrence`：`key`（题内唯一 = `axisSeq` 或 `"unlocated"`）、`axisSeq`、`chapterLabel`、`focus`、`index`、`total`、`isUnlocated`。

### 7.3 幂等语义

| 场景 | 判定 | 响应 |
|---|---|---|
| 带 key，无记录 | 首次 | 201 + 新记录；写 `(key, body_hash, error_id)` |
| 带 key，hash 相同、记录未删 | 重放 | 201 + 原记录 + `X-Idempotent-Replay: 1` |
| 带 key，hash 不同 | 误用 | 409 `IDEMPOTENCY_CONFLICT` |
| 带 key，记录已软删 | 视为未命中 | 201 + 新建；覆盖旧 key |
| 无 key，60 秒内同科同 `rawText` | 指纹 | 201 + 原记录 + `X-Deduplicated: 1` |
| 无 key，`force=true` | 跳过指纹 | 正常新建 |

### 7.4 分页与截断

- `explode=1`：`pageSize` 计「处」；否则计「题」。
- 超过 `scan_cap`：取最近 2000 条，排序退回 `recent`，`sortMeta.truncated=true`，顶部提示——不假装智能排序完整。
- 聚合分层：`points` 对全量扫描集加载；`reviewCount` / `lastRecall` 只对当页聚合。

### 7.5 错误码

`VALIDATION_FAILED`｜`KB_TEXT_TOO_LONG`｜`RESOURCE_NOT_FOUND`｜`IDEMPOTENCY_CONFLICT`。

## 8. 非功能

| 维度 | 要求 |
|---|---|
| 隐私 | 全本地；原文由 `EgressGuard` 拦截；`/error-parse` body 仅 `errorId`（CI 断言） |
| 性能 | 列表 P95 ≤300ms；展开附加 ≤50ms；分位数缓存 60s；复习首题 ≤200ms |
| 批量装载 | `in_()` 分块 500（SQLite 变量上限 999/32766）；语句数不随行数增长；单次列表 ≤3 条查询 |
| 并发安全 | 批量写只提交改动项；展开态键含 `errorId` |
| 降级 | 禁止静默降级；`explode` 与 `sort` 不匹配 → 400 |
| 视觉 | 正式令牌为纸张批注浅色；预演可用深色，但不得写入设计系统 |
| 动效 / 无障碍 | ≤300ms，尊重 `prefers-reduced-motion`；`aria-label` 全覆盖 |
| 文案 | 不用「组卷」；分级词表与分组词表不重叠 |
| 数据体检 | M1 产出 `docs/error-book-data-baseline.md`（`levels` / `module_path` 覆盖率 / `prerequisite` 覆盖率） |

## 9. 验收

**录入与幂等**：题面即存｜连点只一条｜同 key 重放返回原记录｜异 body 409｜命中已删记录则新建｜表态后才 `organized`。

**布局**：四层顺序正确｜数字不随视图移动｜待整理 0 时整段隐藏｜按题去重隐藏不塌陷｜弹层左对齐。

**排序**：单点题与旧版一致｜跨 3 章 28.9%｜跨 8 章 9.4%｜文科 14.9%~29.7%｜无轴 order 不出现｜`levels<2` 不崩溃｜已归档置首｜golden set 通过。

**章节视图**：主副卡数量正确｜副卡就地展开且滚动位置不变｜同题多处独立开合｜同章两道题互不影响｜「本题另见」点击才定位｜轴 none 无入口。

**解释层**：无总分无星形｜主因 ≤12 字｜拆解题固定「跨 N 章」｜贡献合计 100%。

**讲解与复盘**：body 仅 `errorId`｜1 小时内不重复出域｜`degraded=true` 标离线｜复盘数据随 `/mastery` 变化、数据不足不编数。

**复习**：今天模式总数恒 = due｜`due=0` → 「加练一组」｜历史倒序｜读他人历史 404。

**回归**：既有 5 个接口对合法输入形态不变｜6 个卡片动作可达｜全部学科可达｜无新增出域。

## 10. 里程碑

| 里程碑 | 内容 |
|---|---|
| M0 修复批 | N+1 批量装载、讲解接线、幂等、复盘数据源 |
| M1 数据地基 | 迁移 + 数据体检 + 校验与敏感词 |
| M2 排序引擎 | 位置量 + A1–A7 + golden set |
| M3 页面重构 | 四层布局、卡片收敛、收件箱、删假兜底 |
| M4 章节视图 | 主副卡、就地展开、互跳、批量侧重点 |
| M5 复习流 + 对话 | today/extra、明示录入、推断候选 |
| M6 收尾 | 复习历史、来源考试、未定位、配色、文档 |

排序算法（`RANK_CONFIG version 3`）在 M2 一次定稿，M3 之后不再改口径；任何常量调整必须过 golden set。

## 11. 决策台账

| 主题 | 结论 |
|---|---|
| 录入 | 两段式；表态才 organized；幂等 = 指纹 60s + 键 24h |
| 分级 | 1–5 整数星；智能 = 考频 × 掌握度；手改锁定；仅新建与主考点变更重算 |
| 排序 | 三因子加权；权重步长 0.5（v1 无 UI）；顺序轴学科感知；分位数归一；跨度降权 |
| 位置量 | `p_smart` / `p_dedupe` / `p_occ` 三量各司其职 |
| 分组 | 6 组、已归档置首、命中即止 |
| 布局 | 顶栏右＝视图簇；操作行左＝筛选/排序；数字不动 |
| 呈现 | 分组主视图；章节平铺；副卡就地展开、同权、互跳 |
| 解释 | 主因 + 三条贡献占比；排序分只在 `?debug=1` |
| 标签 | 学科独立池；不参与 mastery；支持合并 |
| 复习 | 全屏流双入口；总数恒 = due；历史只读不参与排序 |
| 遗留 | 收藏转错题、拍照录入（P2）；复习失败次数接入分级（单独立项） |

## 附录 A · 学科预置标签

数学：函数与导数、三角函数、数列、立体几何、解析几何、概率统计、压轴题
物理：力学、电磁学、热学、光学、实验题、压轴题
化学：方程式、物质的量、元素化合物、反应原理、有机、实验题
生物：细胞、遗传、稳态、生态、实验设计
语文：文言实词、文言句式、诗歌鉴赏、现代文阅读、作文、默写
英语：语法、完形、阅读、写作、听力、词汇
历史：时间线、史料分析、古代史、近代史、世界史
地理：自然地理、人文地理、区域地理、图表判读
政治：经济生活、政治生活、文化生活、哲学、时政
其他：未分类

## 附录 B · 术语

`p_smart` 智能位置量｜`p_dedupe` 去重位置量｜`p_occ` 单处位置量｜`is_split` 是否拆解｜`span_p` 跨度（百分位差）｜`I_sub` 学科信息量｜`I_item` 题目信息量｜`levels` 有效档数｜`β` 重点 / 最后加权比｜`bucket` 分组｜`stage` 整理状态｜`degraded` 讲解降级标记

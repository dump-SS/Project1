# 知识引用协议（D → F / B / E）

> 版本：**v1.0 · 2026-09-29 冻结** · 产出方：**D 板块**（知识、题本与 AI 辅导）
> 状态：**文本已冻结，实现跟进**。消费方（F / B / E）**按本文本开发即可，不必等 D 的接口实现**。
> 关联：`refactor-module-contracts.md` §3.3、`product-redesign-target.md` D47 / D48 / #40b。
> 上游依据：`openapi.yaml` v1.6.0 的 `KnowledgePoint` / `PointMasteryResult`（字段名以契约为准，本协议不另起）。

---

## 0. 一句话

凡是要"指一个知识点"的地方（题目排序的价值遴选、搜题意图路由、收藏的来源标注、引用块里挂知识点），**统一用这一个结构**：

```jsonc
{
  "pointId": "kp_xxxxxxxxxxxx",   // string | null —— 库外知识恒为 null
  "subjectCode": "SX",            // string | null —— 库外且学科不可知时为 null
  "name": "复合函数单调性",        // string，必填，展示用
  "mastery": 0.42                 // number | null，可省略；见 §2
}
```

四个字段，**不增不减**。消费方不得自行扩展字段（要加字段走 X0 契约变更）。

---

## 1. 字段定义

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `pointId` | string \| null | ✅（可为 null） | `kb_points.id`（`kp_` 前缀） | **库外知识恒为 `null`**，这是"这条知识不在库里"的唯一判定依据 |
| `subjectCode` | string \| null | ✅（可为 null） | `kb_points.subject_code` | 如 `SX`。库外且学科不可知时为 `null` |
| `name` | string | ✅ | `kb_points.name` | 展示用名称；库外知识填用户/模型侧的说法原文，不编造库内名称 |
| `mastery` | number \| null | ❌ 可选 | `kb_point_mastery.mastery` | 0–1；**样本 <3 或从未计算时为 `null`** |

字段语义严格对齐契约 `KnowledgePoint`（pointId / subjectCode / name）与 `PointMasteryResult`（mastery / dataSufficient / sampleSize），**不另起字段名**。

---

## 2. `mastery` 的三条硬口径（消费方必须遵守）

1. **`null` ≠ 0**：`mastery = null` 表示"数据不足/未计算"，**不是"掌握度为 0"**。
   UI 上显示「积累中」或「—」，不得渲染成 0%。（与 C 板块 `self_report_sub = None` 不为 0.0 是同一条原则。）
2. **省略与显式 null 等价**：消费方一律按 `mastery ?? null` 处理，不得因字段缺失而报错。
3. **只有"有错因"的错题才喂 mastery**（D48）：D 侧保证 `kb_point_mastery` 的样本只消费 `error_cause` 非空的错题；
   `intent` 维度（想复习 / 好题 / 典型 / 有疑问）**不进 mastery、不影响数值**——消费方若看到某点 mastery 与题本条目数对不上，这是预期行为，不是 bug。

---

## 3. 库外知识（#40b）

| 场景 | 结构 | 处置 |
|---|---|---|
| 知识点在库内 | `{pointId: "kp_…", subjectCode: "SX", name: "…", mastery: 0.42}` | 正常参与掌握度、可评测 |
| 知识点**不在库内** | `{pointId: null, subjectCode: "SX" \| null, name: "…", mastery: null}` | **只进画像归因**（B 的 `attribution` 组），**绝不硬塞进 mastery** |

> 硬塞会污染掌握度（#40b）。D 侧的接口在库外场景下**不写** `kb_point_mastery`，从源头杜绝。

---

## 4. 三个消费方怎么用

### 4.1 F · 题目排序的价值遴选（D58）

- 排序输入是一组题目，每题携带零个或多个本协议的引用。
- **去重按 `pointId`**（`pointId = null` 的条目按 `name` 归一化后去重，避免同一库外说法重复计数）。
- **排序依据 `mastery` 升序**（掌握度低的优先练）；`mastery = null` 的条目**排在最后且不参与"薄弱优先"权重**——数据不足不该被当成"最薄弱"。
- `pointId = null`（库外）**不参与遴选**，只作为展示标签。

### 4.2 B · 搜题意图路由与引用块

- D 的搜题/讲解结果回传本协议结构，B 用它做意图路由与上下文注入。
- 挂到 B 的引用块协议（`refactor-module-contracts.md` §3.1）时，形态固定为：

  ```jsonc
  {
    "type": "knowledge_point",           // §3.1 已定的五种 type 之一
    "title": "复合函数单调性",            // = 协议的 name
    "payload": { "pointId": "kp_…", "subjectCode": "SX", "name": "…", "mastery": 0.42 },
    "display": { /* 渲染数据，D 侧给出，B 不解析 */ }
  }
  ```

- `payload` **就是本协议结构**（不多不少）；`display` 由 D 侧产出，B 原样渲染、不解析其内部字段。
- 添加到主对话时只带显式输入输出（#45），**不带 mastery 的推导过程**。

### 4.3 E · 收藏来源标注

- 收藏的 `source_ref_json` 里存本协议结构（作为"这条收藏来自哪个知识点"）。
- 库外知识的收藏：`pointId = null` 照样可收藏（收藏不要求可评测），E 侧**不得因为 `pointId` 为空就拒绝或隐藏来源**。
- 与 D47 的关系：题本 + 知识点记录 → 知识页（可复习可评测）；chat 收藏 → 个人中心（不可评测）。本协议只管"引用长什么样"，**不管归位**。

---

## 5. D 侧的实现承诺

| 承诺 | 落点 |
|---|---|
| 构造逻辑单一来源 | 后端 `routes/` 内统一构造函数，前端不在组件里手工拼装 |
| 前端类型 | 随本板块服务层导出（`services/` 内），组件只消费不定义 |
| 库外不写 mastery | 接口层拦截，从源头保证 §3 |
| 契约登记 | 以变更单形式提请 X0 将本协议登记为契约 schema（建议名 `KnowledgeRef`），**登记前字段名即按本文执行** |

---

## 6. 未决 / 不在本协议范围

- **难度双层（D13）**：`difficulty`（1–5）目前**不在**本协议四个字段内。若 F/B/E 排序需要，另行提变更单，不由消费方自行塞进 `mastery` 或 `name`。
- **`code`（如 `SX.func.monotonicity`）**：契约 `KnowledgePoint` 有此字段，但本协议不暴露——消费方需要稳定标识请用 `pointId`，不要用 `code` 做业务判断。
- 图谱关系（prerequisite / derived / contrast / applied_in）走 `KnowledgePointRelation` schema，与本引用协议无关。

---

## 7. 变更规则

本协议**冻结**后，任何字段增改必须：改 `docs/openapi.yaml`（X0）→ 同步本文 → 通知 F / B / E 三个消费方。
消费方发现本文与实现不一致，**以实现为准并立即回写本文**。

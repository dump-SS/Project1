# C → X0 需求单：`self_report` 可空化 + 记录来源字段

> 版本：v1.0 · 2026-09-25 · 提出方：**C 板块**（计划·计时·记录·考试）· 接收方：**X0**（契约与数据平台）
> 性质：**待评审的契约/表变更需求**，不是已定稿。三条需求各自独立，可分开拍板。
> 背景：C 板块 M2 落地时撞到三处硬阻塞，均为「表与契约的必填约束 > 产品口径要求」。
> 关联：`product-redesign-target.md` §3.7(a)、`refactor-decision-mapping.md` D20 / D34 / D49。

---

## 0. 一句话

**`learning_records` 的自评四列是 `NOT NULL`，而目标态有三处明确要求"自评软字段可以缺失"。**
这三处现在都只能靠"造数"或"不做"绕过——按 D34「宁缺毋滥、不造数」的口径，只能选择不做。
所以请在 pilot 删档窗口内放开约束（现在改零成本，beta 起不删档就要带迁移）。

---

## 1. 现状（已实测）

| 位置 | 事实 |
|---|---|
| `backend/models/learning_record.py:46-49` | `self_report_focus` / `self_report_fatigue` / `self_report_emotion` / `self_report_difficulty_feel` 四列**全部 `nullable=False`** |
| `docs/openapi.yaml` → `RecordSelfReport` | `focus` / `fatigue` / `emotion` / `difficultyFeel` **四个都 required** |
| `backend/state_engine/adapter.py:54-59` | `self_report["focus"]` 直接下标取值 → 缺字段即 `KeyError`（不是"容忍缺失"） |
| `backend/state_engine/scoring.py:109-113` | `normalize_focus` / `normalize_inverse_fatigue` 只接受 int |

---

## 2. 三条需求

### 需求 A（D20 计时收尾三层形态）：`focus` / `fatigue` / `difficultyFeel` 放开为可空

目标态 §3.7(a) 写死了数值来源策略：

> - **直填（可靠，进算分）**：时长（自动）、完成度、**情绪（三词直填）**
> - **口语转译（软，进算分）**：**专注 / 疲劳 / 难度**由模型从"一句感受"转译
> - **转译不出则缺省**：状态引擎容忍缺失

也就是说 **必填的只有「完成度 + 情绪」**，`focus` / `fatigue` / `difficultyFeel` 是**软字段**。
但现在契约要求四个全传，于是"用户只填了完成度和情绪"这条正常路径**存不下去**。

**请求**：

| 层 | 改动 |
|---|---|
| 表 | `self_report_focus` / `self_report_fatigue` / `self_report_difficulty_feel` → `nullable=True`（**`self_report_emotion` 保持 NOT NULL**，它是直填必填项） |
| 契约 | `RecordSelfReport.required` 收窄为 `[emotion]`；`focus` / `fatigue` / `difficultyFeel` 加 `nullable: true` |

**C 侧配套**（不需要 X0 做）：`state_engine` 的适配与打分要支持"软字段缺失 → 跳过该子项、按可用部分归一化"。
这条与目标态 §3.7(a) 的「核心自评在 → 正常算分；软字段缺则跳过；核心也缺 → `insufficient_data`」一一对应。
⚠️ 这会动到 `state_engine/`（板块契约说"原样保留"）——但那是"别重写"，不是"不能改"；
改动会附完整用例，且 `compute_session_score` 的**现有行为在四字段齐全时逐字节不变**。

### 需求 B（D34 口语转译兜底）：与 A 同一处约束

D34 的验收是「**转译失败不造数**」。当前实现只能二选一：造数，或 400 拒绝用户提交。
放开 A 之后这条自动满足，无需额外改动。

### 需求 C（D49 成绩回填喂状态评估）：`learning_records` 增加来源字段

目标态 §4.9.1 要求「考后**回填成绩** → 喂状态评估与画像」。

**当前做不到，原因是结构性的**：考试成绩是**客观结果**，它**没有自评**——
没有人会为一次期中考试填"专注度 4 分 / 疲劳度 2 分"。而 `learning_records` 强制自评四列，
所以"成绩 → 记录 → 状态评估"这条路必然要造数（正是 D34 禁止的）。

**两个可选方案，请 X0 拍**：

| 方案 | 做法 | 代价 | C 侧评价 |
|---|---|---|---|
| **C-1（推荐）** | `learning_records` 加 `source`（`self_report` / `exam`）+ `source_exam_id`；考试回填成绩时生成一条 `source=exam` 的记录（自评为空、`behavior.accuracy` = 得分率） | 两列 + 契约两个可选字段 | 复用现有状态引擎与 mastery 链路，**不改纯计算层**；来源可追溯（列表/复盘能区分"自评记录"与"考试记录"） |
| C-2 | 不动 records，让 `state_engine` 直接吃 `exams` 作为第二类信号源 | 改纯计算层 + 新窗口语义 | 语义更"干净"，但状态分从"学习过程状态"变成"过程+结果混合"，且要重定义窗口 |

> 在 C-1 落地前，C 侧**只做**：Exam CRUD、Goal 通过 `examId + targetScore` 引用考试、成绩回填落库、
> `GET /exams` 供 E（档案）与 B（画像）消费。**不做**自动生成记录——不造数。

---

## 3. 验收（X0 侧）

- [ ] `alembic upgrade head` 在 SQLite + Neon 各跑通一次，`downgrade` 可回退，`alembic check` 无差异
- [ ] 契约 `RecordSelfReport.required` 收窄后，`$ref` 无断链（本文件所属 PR 里已补过一轮校验脚本）
- [ ] 迁移是**单 head**（勿与其它板块并行出多 head）
- [ ] 若采纳 C-1：`source` 默认 `self_report`，存量行不需要回填（pilot 删档期本就直接重建）

## 4. 时间窗口

pilot 是**删档期**，schema 可激进重建。这三条现在做的成本 ≈ 一次迁移；beta 起不删档后，
要带存量迁移 + 前后端同步发版。**建议在 M2 期间一并做掉。**

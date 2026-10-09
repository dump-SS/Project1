# C → X0 需求单：`self_report` 可空化 + 记录来源字段

> 版本：**v2.0 · 2026-09-25 已落地**（原 v1.0 为需求提出）· 提出方：**C 板块**（计划·计时·记录·考试）
> 状态：**已按本单推荐方案（A + C-1）实现并验证**，待 X0 评审合入。
> 关联：`product-redesign-target.md` §3.7(a)、`refactor-decision-mapping.md` D20 / D34 / D49。

---

## 0. 结论：三条需求全部落地

| 需求 | 落地方式 | 验证 |
|---|---|---|
| **A** `focus`/`fatigue`/`difficultyFeel` 放开为可空 | 迁移 `c7a1f2e4d9b3`；契约 `RecordSelfReport` 去掉 `required`、四项加 `nullable` | `tests/test_self_report_optional.py` |
| **B** D34 转译失败不造数 | 同 A（放开后"缺省"成为正常路径，无需额外改动） | 同上 |
| **C** 记录来源字段（C-1 方案） | `learning_records` 加 `source` + `source_exam_id`；契约新增 `RecordSource` 枚举 | `tests/test_exam_record_linkage.py` |

**实现时发现的一处补充**：`emotion` 也必须可空——三层收尾里「情绪快捷词」本身就写明是
「**可选**兜底」，只有完成度是半强制的。所以 `RecordSelfReport` 是**四字段全可空**、
`RecordInput.selfReport` **可整段省略**，不是只放开三个。

---

## 1. 改了什么（已实测）

| 层 | 改动 |
|---|---|
| 表（迁移 `c7a1f2e4d9b3`，down_revision `b81d83bafb89`，**单 head**） | `learning_records`：自评四列 → `nullable=True`；新增 `source`（NOT NULL，默认 `self_report`）+ `source_exam_id`（可空，带索引）。`exams`：新增 `duration_minutes`（可空） |
| 契约 | `RecordSelfReport` 去掉 `required`、四项加 `nullable`；`RecordInput.selfReport` 可空且 `required` 去掉；`LearningRecord` 加 `source`/`sourceExamId`；新增 `RecordSource` 枚举；`TimerFinish.selfReport` 可省；`StateBreakdown` 自评侧五项可空；`Exam*` 三处加 `durationMinutes`；`GET /learning-records` 加 `source` 过滤 |
| 引擎 `state_engine/` | `SelfReportInput` 四字段可空；`SessionScore.self_report_sub` 可空；`scoring` 缺项**跳过并按可用项权重归一化**；`assessment` 的疲劳/情绪信号改为**从末尾取连续有值项**（遇缺即停）；`adapter` 不再下标取键 |
| 契约版本 | v1.6.0 → **v1.7.1** |

### 三条不可动摇的约束（已写进测试）

1. **四字段齐全时结果与放开前逐字节一致** —— `scoring` 里齐全走原公式、只有缺失才归一化；
   `tests/test_self_report_optional.py::test_full_self_report_matches_legacy_formula` 用数值断言钉死。
2. **不拿 0.0 冒充"没有自评"** —— 自评整段缺失时 `self_report_sub = None`（不是 0），
   `StateBreakdown.selfReportSubAvg` 回 `null` 由前端显示「—」。0.0 的含义是"自评很差"，两者必须区分。
3. **软字段缺失不改变"连续"语义** —— 疲劳/情绪信号判的都是「连续 N 次」，
   过滤掉缺失项会把不连续读成连续（凭空造出"连续负向"的结论），故改为**遇缺即停**。

---

## 2. D49 成绩回填 → 状态评估：落地口径

回填 `PATCH /exams/{examId}` 的 `score` 后，自动维护一条 `source=exam` 的学习记录：

| 项 | 取值 | 为什么 |
|---|---|---|
| `selfReport` | **整段为空** | 考试没有自评，绝不编数据 → 引擎走"自评不可用 → 只按行为子分计"的降级 |
| `behavior.completion` | `completed` | 考试确实完成了（客观事实） |
| `behavior.accuracy` | `score / fullScore` | 得分率，进状态公式的行为子项 |
| `durationMinutes` | `Exam.durationMinutes` | **只有这一处来源**。没填 → **不生成记录**（宁可少一条，也不编时长） |
| `startedAt` | 考试当天 00:00 | 考试只精确到日期，不编一个"看起来像真的"时刻 |
| `note` | `「{考试名} · 成绩回填」` | 让这条记录在列表里自解释 |

配套行为（都有测试）：**幂等**（改分数只更新同一条，不会在窗口里多出记录）、
**撤回即删除**（传 `score: null` 连带删记录）、**删考试连带删记录**、**不触发建议生成**。

> 若产品后续要求"成绩只做客观锚点、完全不进状态窗口"，改一行即可：
> `record_service.window_rows()` 里加 `source == 'self_report'` 过滤。字段已就位，不必再改表。

---

## 3. 给 X0 的评审要点

- [ ] 迁移是否**单 head**（当前 `alembic heads` = `c7a1f2e4d9b3`）——若与其它板块并行出了新迁移，需合并 head
- [ ] 是否接受**契约版本 v1.7.1**（本轮为纯增量：无字段改名、无枚举取值变更）
- [ ] `source` 的默认值语义：存量行（pilot 删档期本就直接重建）无需回填
- [ ] 若采纳「成绩不进状态窗口」的口径，告知 C 侧，一行过滤即可切换


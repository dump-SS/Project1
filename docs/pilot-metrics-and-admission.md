# pilot 核心指标与阶段准入标准（#53）

> 版本：v0.1 · 2026-09-25 · 责任板块：G
> 性质：**成文基线**。指标口径现在锁定（决定埋什么点，D39）；准入阈值中标注「待拍板」的数值需 Skyer 确认后升 v1.0。
> 数据来源约束：**pilot 指标必须能从 `analytics_events`（D39 三块）+ `usage_ledger` + 既有业务表直接读出**，不允许「为了看指标再加一套埋点」。M6 验收门「pilot 指标可从埋点直接读出」以本文件为对照标准。

---

## 0. 阶段定义（#53 口径）

| 阶段 | 数据 | 收费 | 准入含义 |
|---|---|---|---|
| **pilot** | 删档测试 | 不收费（记 usage_ledger 数值成本） | 验证产品价值与合规底线，名额制（邀请码 #50） |
| **beta** | 不删档（需迁移方案，届时另评） | 启动收费评估 | pilot 达到准入标准后进入 |
| 正式 | 不删档 | 收费 | 另行成文 |
| 2.0 | — | — | 桌面端 + agent harness（harness 决策见 `desktop-timing-assessment.md`，未拍板） |

---

## 1. pilot 核心指标（口径锁定，埋点就位后即可读）

### 1.1 用户价值（决定 pilot 成败的主指标）

| 指标 | 定义 | 数据来源 | 目标（待拍板） |
|---|---|---|---|
| 激活率 | 注册 → 建档完成（onboarding_completed）比例 | users 表 | ≥ 70% |
| 次周留存 | 注册后第 7 天仍有学习记录或对话 | learning_records + chat_sessions | ≥ 25% |
| 首日闭环完成率 | 当日内走通 计划→计时→记录 至少一次 | plans/timer_sessions/learning_records | ≥ 40% |
| Chat 活跃度 | 日均每人 message_sent 轮次 | analytics_events(chat_interaction) | 观察项，不设阈值 |

### 1.2 AI 质量（决定信任的护栏指标）

| 指标 | 定义 | 数据来源 | 目标（待拍板） |
|---|---|---|---|
| 报错率 | 消息级 error_reports / message_sent | error_reports + analytics_events | ≤ 5% |
| 反馈有用率 | feedback rating=useful 占比 | 既有 feedback 接口（assessments/recommendations/summaries） | ≥ 60% |
| 卡片点击率 | card_clicked / card_shown | analytics_events(chat_interaction) | ≥ 30% |
| 意图纠正率 | intent_corrected / message_sent | analytics_events(chat_interaction) | ≤ 10% |
| 危机响应触发正确率 | 人工评审抽样：应转介场景 100% 走 L3 固定文案 | 评审记录（不进埋点，抽样人工） | 100%（红线，非目标而是底线） |

### 1.3 画像信任（D50 信任基础设施是否成立）

| 指标 | 定义 | 数据来源 | 目标（待拍板） |
|---|---|---|---|
| 画像查看率 | 进入画像管理页的用户占比 | analytics_events(profile_trace) | 观察项 |
| 画像改删率 | 用户修改/删除条目数 / 提取条目数 | analytics_events(profile_trace) | ≤ 30%（过高 = 提取质量不可信） |

### 1.4 成本（pilot 不收费但必须可算，为 beta 收费评估留数）

| 指标 | 定义 | 数据来源 | 目标（待拍板） |
|---|---|---|---|
| 单用户月成本 | 当月 usage_ledger.cost 合计 / 活跃用户数 | usage_ledger | 观察项，无预算红线前不设阈值 |
| 档位成本结构 | chat / embedded / advanced / multimodal 成本占比 | usage_ledger（feature_tier） | 观察项 |
| 嵌入式占比 | embedded 档成本占比（D38：embedded 不进 credits） | usage_ledger | 观察项 |

### 1.5 合规与安全（红线，不达标一票否决）

| 项 | 判据 | 数据来源 |
|---|---|---|
| 数据不出域 | 错题/学习记录 embedding egress 测试断言全绿（egress CI） | X2 CI |
| 撤回即删除 | 撤回授权后特征行物理删除（≤24h） | community_jobs 留痕 |
| 监护人授权 | 13-15 岁用户社区/数据共享功能全部有有效授权门槛 | guardian_authorizations |
| 违规处置留痕 | violation_logs 每次处置可追溯，阶梯执行正确 | violation_logs（#43） |
| 原文 TTL | chat_raw_messages 30 天到期物理删除，job 运行留痕 | TTL job 日志（D45） |

---

## 2. pilot → beta 准入标准（建议稿，数值待 Skyer 拍板）

**全部满足才准入；任何一条不满足即延长 pilot。**

1. **功能完备**：重构 M0–M6 全部验收门通过；四档清单中「pilot 必做」项 100% 完成（`refactor-development-plan.md` §5）。
2. **质量稳定**：连续 4 周后端 5xx 率 ≤ 1%；全量 pytest + 契约测试 + egress CI 持续绿。
3. **核心指标达标**：§1.1 中激活率、次周留存、首日闭环完成率达到拍板阈值；§1.5 合规红线零违反。
4. **样本充分**：累计激活用户 ≥ 50（pilot 名额制下的实际可达数，待拍板），且指标覆盖至少一个完整月。
5. **成本可算**：§1.4 三项成本指标可从 usage_ledger 直接读出，并形成 beta 定价评估输入（付费评估本身仍推迟到 pilot 后，#30）。
6. **协议就位**：#29a 协议与条款上线前补齐（登录前可读），与未成年付费同级的高优合规项。
7. **桌面端决策不阻塞**：桌面端「壳」是否前移 beta 以 `desktop-timing-assessment.md` 拍板为准，**不纳入本准入标准**（该文档明确为决策前置材料，尚未拍板）。

---

## 3. 埋点与指标的对应关系（防「指标有了埋点没埋」）

| §1 指标 | 依赖的埋点/表 | 落地板块 |
|---|---|---|
| Chat 活跃度、卡片点击率、意图纠正率 | analytics_events: message_sent / card_shown / card_clicked / intent_corrected | B（chat_interaction） |
| 报错率 | error_reports + message_sent | G（已交付 POST /error-reports）+ B（消息级挂 ErrorReportButton） |
| 反馈有用率 | assessments/recommendations/summaries feedback（已有接口） | 既有 |
| 画像查看率、改删率 | analytics_events: profile_viewed / profile_edited / profile_deleted / profile_extracted | B（profile_trace） |
| 单用户月成本、档位结构 | usage_ledger（✅ 已交付：llm_provider 出口写入） | G（✅） |
| 违规处置 | violation_logs（✅ 已交付：阶梯 + 留痕） | G（✅）+ B（输入侧检测触发 record_violation） |

> ⚠️ B 板块的 chat_interaction / profile_trace 事件名在接入时以本表为准扩展，
> 事件名变更属契约 eventType 描述的更新，走 X0 评审。

---

## 4. 未决项

- §1 各表「目标（待拍板）」列：由 Skyer 拍板后本文件升 v1.0。
- pilot 名额规模与邀请码发放节奏（#50 的运营侧）：影响 §2.4 样本标准的可行性。
- 桌面端前移 beta（`desktop-timing-assessment.md`）：拍板后若前移，本文件 §2 增补桌面端验收条目。

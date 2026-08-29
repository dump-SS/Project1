# 板块三「群体匿名参照」开发计划方案

- 版本：v1.0
- 日期：2026-08-29
- 依据：PRD v1.4（§2、§8.1、§10.2、§10.3）、`module3-privacy-review.md`、`module3-statistics-view-design.md`、`module2-3-as-built-vs-plan.md`、`module2-backlog.md`、`module2-next-iteration-tasks.md`、`module2-3-gap-architecture-api-checklist.md`
- 定位：板块三从「架构预留」转入「正式立项实施」的开发计划。前提：模块二收尾工作按 backlog 并行推进，本计划已评估其影响并预留应对（见第 7 节）

---

## 1. PRD 对板块三的要求摘要

| 出处 | 要求 | 对实现的约束 |
|---|---|---|
| §2 / §10.2 | 只上传匿名特征值（状态标签分布、某类学习方法的效果统计等），跨用户群体状态/方法对比参照，**不上传任何原始学习内容** | 上传字段白名单制；原文/自评文本/错题内容一律禁传 |
| §10.2 | 需要匿名化/脱敏规则和**最小群体规模限制**（避免小样本反推个体），专门的**隐私工程评审是合规上线的前置条件**，不能等做完了再补 | k≥20 硬校验（预评审已定）；评审通过前不上传真实数据 |
| §10.3 | 板块三只消费板块一/二产出的**匿名化统计特征**；任何「匿名聚合」都应是**显式的、用户可感知的授权动作**，不能是默认行为；为「匿名特征提取」预留**独立的统计视图层**，不改板块一/二原始数据结构 | 特征抽取走独立视图层/独立表；授权默认关闭、显式开启、可撤回 |
| §8.1 | 未成年人场景：「匿名」不构成免责，授权链路需与监护人授权一致 | 监护人授权文案 v1.5 须含板块三专款（搭车模块二 D2） |

## 2. 现有进度盘点（预留期已交付项）

| # | 项 | 状态 | 位置 |
|---|---|---|---|
| 3-A | 演示页「演示数据」水印 | ✅ 已交付（PR #36） | `components/CommunityDemoBadge` |
| 3-B | 统计视图层设计（k≥20、`COMMUNITY_INSUFFICIENT_POOL`、只发聚合不发个体、数据流图） | ✅ 已交付 | `module3-statistics-view-design.md` |
| 3-C | 隐私工程预评审（7 项风险定级 + 4 条放行条件，结论：风险中等偏高，预评审不立项） | ✅ 已交付 | `module3-privacy-review.md` |
| 3-D | 契约预留：`POST /community/features`、`GET /community/aggregate`、`GET/PUT /me/community-consent`（x-status: planned，501 占位） | ✅ 已交付 | `openapi.yaml`（1.5.0） |
| — | 前端演示页：`/community/upload` + `/community/compare` | ⚠️ 演示雏形，需改写 | `pages/Community/`（纯 localStorage：`community_my_data` / `community_pool`，Compare.tsx 在**前端本地计算他人个体特征**，违反「只发聚合不发个体」原则，转正时必须重写） |

**已具备的复用基础**（来自板块一/二建设，板块三可直接复用）：

- `EgressGuard` 白名单/黑名单机制（`backend/egress_guard.py`）——板块三上传字段管控沿用同一思路（方向相反：只允许特征值枚举通过）；
- `users.knowledge_ai_egress_enabled` 开关模式 + alembic 增量迁移规范——`community_consent_enabled` 照此办理；
- `rate_limit` 持久化限流表（T5 已交付）——聚合接口防差分攻击的查询限频直接复用；
- `jobs/weekly_knowledge_summary.py` 定时任务模式——聚合预计算 job 沿用；
- 学科代码已全面切换为拼音大写（`SX/WL/YY/...`，契约 `Subject` 枚举已对齐），前端 Community 页取值一致，无需再做代码层转换。

## 3. 演示版 → 合规版差距清单

| # | 差距 | 现状 | 目标态 |
|---|---|---|---|
| G1 | 授权链路 | 无（localStorage 模拟即参与） | 默认关闭；显式开启；随时撤回；监护人授权文案覆盖 |
| G2 | 特征上传 | 无后端，数据只存浏览器 | `POST /community/features` 真实上传，字段白名单 + CI 断言 |
| G3 | 聚合计算 | Compare.tsx 前端本地算个体池 | 服务端预计算分位数/直方图桶，前端只读聚合结果 |
| G4 | 小样本保护 | 无 | k≥20 双重校验（聚合时 + 查询时），不足返回 `COMMUNITY_INSUFFICIENT_POOL` |
| G5 | 差分攻击防护 | 无 | 查询维度白名单 + 限频；聚合只读物化结果，不开放实时任意维度查询 |
| G6 | 撤回语义 | 无 | 撤回即停止后续上传 + 历史特征不再参与聚合（实现方案见 5.2，物理删除策略随正式评审定稿） |
| G7 | 水印延续 | 演示页有 | 所有板块三入口在数据未达真实规模前保留「数据积累中/演示」标识 |

## 4. 阶段总览与排期

| 阶段 | 内容 | 前置条件 | 估算 |
|---|---|---|---|
| **M0 评审与决策**（非代码，并行推进） | 正式隐私工程评审；法务评审（授权文案 v1.5 板块三专款）；k 值/分桶宽度/差分噪声决策；特征清单白名单评审 | 预评审纪要（已有） | 1-2 周（等待为主） |
| **M1 契约转正 + 授权链路** | openapi planned → 正式契约；`community_consent_enabled` 开关 + 迁移；`/me/community-consent` GET/PUT | M0 特征清单定稿 | 3 人日 |
| **M2 特征抽取与上传** | `community_features` 表（统计视图层）；特征抽取 job（板块一数据 → 分桶脱敏特征）；`POST /community/features` + 白名单校验 + CI 断言 | M1 | 4 人日 |
| **M3 聚合层** | 聚合预计算 job（分位数 + 直方图桶，k≥20）；`GET /community/aggregate` 读物化表；查询限频 | M2 | 4 人日 |
| **M4 前端转正** | Upload 走真实接口 + 授权态联动；Compare 重写为只消费服务端聚合；数据不足/未授权/降级三态；水印延续 | M3 | 4 人日 |
| **M5 验收** | 隐私 CI 断言、差分攻击场景测试、降级矩阵（并入模块二 T12）、演示走查 | M4 | 2 人日 |

单人串行约 **17 人日**（不含 M0 评审等待）。关键路径：**M0 → M1 → M2 → M3 → M4 → M5**。M0 评审期间可先行动手 M1 的契约草稿与迁移（特征清单评审若有调整再回改），但不合入主干。

## 5. 各阶段设计要点

### 5.1 M1 契约转正 + 授权链路

- **契约**：将 `openapi.yaml` 中 3 条 planned 接口转为正式定义，补齐请求/响应 schema 与错误码：
  - `POST /community/features`：请求体为特征值枚举对象（见 5.2 字段表），响应 202；错误码 `COMMUNITY_CONSENT_REQUIRED`（未授权）、`COMMUNITY_INVALID_FEATURE`（白名单外字段/越界值）；
  - `GET /community/aggregate?subject=&metric=&stage=`：响应为 `{ poolSize, percentiles: {p25,p50,p75}, histogram: [{lo,hi,count}] }`；错误码 `COMMUNITY_INSUFFICIENT_POOL`（k<20）、`RATE_LIMITED`（沿用统一格式）；
  - `GET/PUT /me/community-consent`：`{ enabled: bool, updatedAt }`。
  - `metric` 枚举与分桶边界在契约中固化（与前端 `METRICS` 对齐：hours/focus/fatigue/completion，后续增 mastery 时契约增量扩展）。
- **授权开关**：`users` 表增 `community_consent_enabled: bool = false`（仿 `knowledge_ai_egress_enabled`），alembic 增量迁移带默认值；Settings 页加开关 + 板块三隐私说明文案（文案定稿依赖 M0 法务）。
- **监护人联动**：监护人授权失效（`GUARDIAN_AUTHORIZATION_EXPIRED`）时上传接口同步 403；`community_consent` 随监护人授权撤销一并关闭。

### 5.2 M2 特征抽取与上传（统计视图层）

- **新表 `community_features`**（独立命名空间，不改板块一/二原始表）：

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `anon_participant_id` | 匿名参与 ID = `HMAC(user_id, server_salt)`，**不可反查**，用于撤回删除（见下） |
| `period` | 统计周期（如 `2026-W35`），聚合按周期滚动 |
| `subject` / `stage` | 分组维度（stage=junior/senior） |
| `hours_bucket` / `focus` / `fatigue` / `completion_bucket` | 特征值（数值或分桶，白名单枚举内） |
| `created_at` | 时间戳 |

- **撤回语义（G6）**：撤回时按 `anon_participant_id` 删除该用户全部历史特征行（推荐方案——既满足「撤回即退出聚合池」，又解决预评审 #6「历史特征留库」问题，且 HMAC 不可逆不泄露身份；salt 存服务端环境变量不落库）。备选方案「只停用不删除」在正式评审中对比定稿，代码上按可切换实现。
- **抽取路径**：双通道——① 客户端上报（用户在 Upload 页确认本周数据后调 `POST /community/features`，服务端只接受白名单字段与合法区间，不信任客户端计算）；② 服务端特征抽取 job（周更，从 `learning_records`/`state_assessments` 计算授权用户的特征并 upsert，作为通道①的校正源，最终聚合以服务端抽取为准）。
- **上传管控**：请求字段白名单硬编码（仿 EgressGuard 反向使用），出现白名单外字段直接 400 + audit log；新增 `tests/test_community_egress_ci.py` CI 断言：原文/身份类字段名（复用 EgressGuard 黑名单 15 键）出现在上传 payload 即测试失败。

### 5.3 M3 聚合层

- **新表 `community_aggregates`**（物化结果）：`subject × stage × metric × period` 一行为 `{ pool_size, p25, p50, p75, histogram_json, computed_at }`。
- **预计算 job**（`jobs/community_aggregate.py`，日更低峰）：对每个维度组合计算分位数与直方图；**pool_size < k=20 的组合不落结果行**（查询侧自然返回 `COMMUNITY_INSUFFICIENT_POOL`），实现 k 值的第一重校验；查询接口再校验一次（第二重）。
- **查询接口只读物化表**，不提供实时任意维度聚合——从根上防多次查询拼接反推（预评审 #7）；查询参数维度白名单 + `rate_limit` 表限频（如每用户每分钟 10 次）。
- **差分隐私噪声**：M0 评审定是否引入；实现上在 job 的分桶计数处预留噪声注入点（不改接口形态）。

### 5.4 M4 前端转正

- `pages/Community/community.ts`：删除 `community_pool` 本地模拟池与前端百分位计算，改为调用 `GET /community/aggregate`；`community_my_data` 仅保留「我的本周数据」草稿语义。
- `Upload.tsx`：接入授权态——未授权时展示授权引导（跳 Settings 开关或页内 inline 开启）；已授权走真实上传；提交成功提示「已匿名参与」。
- `Compare.tsx`：只渲染服务端下发的分位数/直方图 + 「我的位置」标记（我的数值由本端持有，不与池混合计算）；`COMMUNITY_INSUFFICIENT_POOL` 时展示「群体数据积累中（还差 X 人）」空态——沿用「数据不足不硬凑结论」的产品原则（PRD 5.2 冷启动精神）。
- 所有入口延续 `CommunityDemoBadge` 体系：聚合池达到真实规模门（建议 k 连续 4 周期达标）前，页面保留「数据积累中」标识。
- 降级：聚合接口失败 → 展示缓存的上次结果 + 「数据更新延迟」提示，不白屏（并入模块二 T12 降级矩阵）。

### 5.5 M5 验收标准（上线门）

1. 上传白名单/黑名单 CI 断言全绿；原始学习内容、身份字段 100% 不可上传；
2. k<20 的所有维度组合均返回 `COMMUNITY_INSUFFICIENT_POOL`，无任何个体数据泄露路径（含多次查询拼接场景测试）；
3. 撤回授权后：上传被拒、历史特征不再出现在下一周期聚合中（anon id 删除路径生效）；
4. 监护人授权失效时板块三写接口 403；
5. 正式隐私工程评审 + 法务评审（文案 v1.5 板块三专款）通过；
6. 降级矩阵四态（未授权/样本不足/聚合未生成/服务不可用）走查无空白页；
7. 授权默认关闭，开启动作为显式用户操作并有告知文案。

## 6. 数据出域边界对照（板块三不涉及 LLM 出域）

板块三无 LLM 调用、无第三方传输，隐私风险集中在**服务端内的匿名化强度**。与板块二 12.6 的对照：板块二管「出域前过滤」，板块三管「入库前脱敏 + 出库前聚合」。两道防线独立，互不复用数据——板块三不读 `kb_*` 原文表，特征来源仅限 `learning_records` / `state_assessments` 的数值字段与（v3.2 起）`kb_point_mastery` 的 mastery 数值。

## 7. 模块二收尾工作的影响与应对措施

模块二剩余项（backlog + next-iteration-tasks 口径）对板块三的影响评估：

| 模块二剩余项 | 对板块三的影响 | 应对措施 |
|---|---|---|
| **D1 正式内容清单导入**（kb_points 7 内容字段已建表，内容导入未完成） | mastery 数据稀疏 → 「群体掌握度对比」特征价值低、样本难达 k=20 | **特征清单分两批**：M2 只含板块一行为/状态特征（hours/focus/fatigue/completion）；mastery 特征列为增量（契约预留枚举位），按「授权用户中 mastery 覆盖率 ≥60%」为启用门，不达标不上线该指标 |
| **D2 监护人授权文案 v1.5 法务评审**（模块二 backlog D 类） | 板块三专款须搭车同版文案，是 M5 上线门硬前置 | 若 D2 延期：M1-M4 照常开发但**功能开关默认关闭 + 上传接口灰度关闭**，只做内测数据；文案通过后开闸。M0 阶段即向法务提交板块三专款草稿，避免串行等待 |
| **T10 性能压测未执行** | 聚合接口性能基线未知，可能挤占板块一/二链路资源 | 架构上解耦：聚合走**预计算物化表**，在线查询 O(1) 读表，不进入 T10 压测关键路径；板块三自身的聚合 job 耗时与查询 P95 并入 T10 一并补测（增加 `/community/aggregate` 压测场景） |
| **T12 降级矩阵未执行** | 板块三新增 4 个降级态需覆盖 | 不另起炉灶，**并入 T12**：矩阵扩展「未授权 / 样本不足 / 聚合未生成 / 服务不可用」四态，一次走查同时覆盖板块二与板块三 |
| **B4 进程内并发队列未做** | 特征抽取/聚合 job 若与 LLM 生成并发竞争，单进程 BackgroundTasks 下可能相互拖慢 | 聚合 job 排低峰定时（沿用 `jobs/` 模式），特征抽取为周更小批量；不与 LLM 调用路径共用队列。B4 落地时板块三 job 一并迁入，无需改接口 |
| **T9 OCR 决策 / T11 演示脚本 / C1 薄弱路径高亮 / C4** | 无直接耦合 | 演示脚本（T11）固化的 5 场景不含板块三，板块三演示走查在 M5 自行补充，不阻塞 |
| **学科代码切换（已完成，SX/WL/YY）** | 契约 `Subject` 枚举与前端 Community 取值已对齐 | M1 契约转正时核对 `metric` 枚举、分桶边界与前端 `METRICS` 一致即可，无迁移负担 |

**总体判断**：模块二收尾不构成板块三开发的阻塞项；唯一硬依赖是 **D2 法务文案**（卡上线门而非卡开发），已通过「功能默认关闭 + 文案提前送审」消解。建议板块三 M0 评审与模块二 T10/T12 验收**并行排期**，避免串行。

## 8. 风险登记册

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | 正式隐私工程评审提出超预期整改（如强制差分隐私、更高 k 值） | 高 | M0 前置启动评审；k 值与分桶参数配置化（不落代码常量），评审结论只需改配置 |
| R2 | 真实用户量不足，聚合池长期达不到 k=20 | 高 | 前端「数据积累中」空态即产品答案；上线初期可与演示数据混排但**水印必须保留**直至连续 4 周期真实达标（需产品决策确认，避免误导） |
| R3 | 未成年人「匿名」授权被质疑（监护人不知情） | 高 | 授权开关纳入监护人授权体系，监护人确认链接中可一并查看/关闭；文案法务评审 |
| R4 | HMAC salt 泄露导致 anon_participant_id 可批量碰撞 | 中 | salt 走环境变量 + 定期轮换（轮换时旧特征自然过期，聚合按周期滚动不受影响） |
| R5 | 前端 Compare 重写后体验退化（本地实时计算 → 依赖服务端聚合周期） | 低 | 聚合日更 + 上传后立即返回当前周期最新物化结果，感知延迟 < 24h 可接受 |

## 9. 与既有文档的关系

- 执行层状态追踪：板块三任务落地后在 `module2-backlog.md` 增「板块三」分区或新建 `module3-backlog.md`（建议后者，板块二 backlog 归档后）；
- 契约变更先改 `docs/openapi.yaml`（M1），x-status 从 planned 移除并补全 schema；
- 评审结论回填：`module3-privacy-review.md` 追加正式评审章节（预评审 4 条放行条件逐条核销）。

# EpochX 重构落地实施方案（主计划）

> 版本：v1.0 · 2026-09-18 · 基线：HEAD `736461a`
> 定位：多人 / 多 agent 并行开发的总控文档。只规定**阶段、依赖、范围、验收**，不写视觉细节。
> 配套文档（四件套，缺一不可）：
> - [refactor-decision-mapping.md](./refactor-decision-mapping.md) — D1–D59 与执行项的全量归属表（验收索引）
> - [refactor-module-contracts.md](./refactor-module-contracts.md) — 板块所有权、共享协议、文件独占表
> - [refactor-migration-checklist.md](./refactor-migration-checklist.md) — 现有页面/接口/表的处置清单
> 上游依据：[product-redesign-target.md](./product-redesign-target.md) v0.29（目标态）· [refactor-2026-09-feature-ia-logic.md](./refactor-2026-09-feature-ia-logic.md) + [refactor-baseline-recheck-2026-09-18.md](./refactor-baseline-recheck-2026-09-18.md)（现状基线与勘误）· [refactor-implementation-notes.md](./refactor-implementation-notes.md)（执行细节）
> 契约铁律：**任何新字段/新实体先改 `docs/openapi.yaml`，未改契约不得写接口。**

---

## 1. 阶段口径（一切排期的前提）

| 阶段 | 数据 | 收费 | 本方案覆盖 |
|---|---|---|---|
| **pilot**（本方案目标） | 删档测试，可清库，schema 可激进，不做导出迁移 | 不收费；**按用户记录模型数值成本**（usage_ledger） | ✅ 全部 |
| beta | 不删档（需迁移方案，届时另评） | 启动收费评估 | ❌ 仅标注 |
| 支付相关 | — | 渠道/充值页/付费条款 **推迟到 pilot 结束后** | ❌ 仅留接口位 |

pilot 合规底线（不因阶段豁免）：监护人授权、撤回即删除、社区 k 值下限、数据不出境（错题/学习记录 embedding 走本地模型）、未成年告知。

## 2. 目标态速览（IA 变化）

```
现状（页面+导航）                      目标态（Chat 为核 + 个人中心为仓）
侧边栏 10 项 + 我的                    首页 = Chat（单对话，无历史列表）
/chat = 前端 mock                      首页 Chat = 真链路，一切动作从对话发起
数据/复盘/建议/目标 四个独立页    →    个人中心（数据+画像+档案+复盘+目标树+社区+收藏+设置）
错题本独立页                      →    并入知识页（题本）
社区前后端双轨（假人）            →    个人中心内社区参照，前端接真 aggregate
OCR 501 占位                      →    删除，统一多模态
```

最大缺口：目标态的核（首页 Chat）在现状里**后端不存在**——这是 M1 的主战场。

## 3. 板块划分与依赖

板块资产与边界的完整定义见 [refactor-module-contracts.md](./refactor-module-contracts.md)。依赖关系（箭头=必须等待）：

```
X0 契约与数据平台（M0）
 ├─→ A 身份·入口·合规（M1）──会话──┐
 ├─→ B Chat 内核·记忆·画像（M1）◀──┘
 │        │（A/B 地基就绪后放号）
 ├─→ C 计划·计时·记录·考试（M2）──┐
 ├─→ D 知识·题本·AI 辅导（M3）────┤──数据消费──→ E 个人中心·收藏·社区（M4）
 │        └─ 知识引用协议 ──→ F 多模态·文件·学科工具（M5）
 │        B ─ 引用块协议 ──→ F
 └─→ G 运营治理（M0 起并行，usage_ledger 必须先于 B 首次真实调用）
X1 前端壳与响应式、X2 QA 安全观测：全程横切，共享入口文件由集成者最后统一收口
```

并行规则：C/D/E 在契约冻结（M0 完成）+ A/B 地基（M1 完成）后可三线并行；F 必须等 B 的引用块协议与 D 的知识引用协议**文本落定**（不必等实现完成）；G 与所有板块并行，唯一硬前置是 usage_ledger。

## 4. 里程碑

### M0 · 契约与数据基线（X0 独占）

范围：
1. **稳定 user_id 改造**（D59）：users 加 email+handle 列、AuthUser 加 user_id、注册改序（先生成 `u_` 短码 id）、session 改存 user_id、openapi 里 `User.userId` 语义更新为稳定 ID。pilot 删档期直接按新 schema 重建，跳过存量迁移。
2. **补 `kb_subjects` 9 行学科数据**——现状该表 0 行，`GET /knowledge/subjects` 必返空（复核已坐实），这是知识链路一切工作的前置。
3. **新实体 schema**：exams、collections/collection_items、usage_ledger、invite_codes、violation_logs、error_reports、medals、画像（user_profiles）、话题摘要（topic_summaries）、讲解归档（explanations）、题本扩展字段（错因/意图/来源考试）。全部先进 openapi.yaml，再出 Alembic 迁移（单 head，只有 X0 能写）。
4. **删除 OCR**：`routes/ocr.py` + main.py 挂载 + 前端入口（若有）一并删，目标态 §3.5 文案同步。
5. Neon Postgres 方言复验（squash 基线只在 SQLite 验过）。

进入条件：无（立即启动）。
验收门（**2026-09-19 全部达成**，实测记录见下）：
- [x] 空库 `alembic upgrade head` 通过（SQLite + Neon 各一次）—— 迁移 `5015e9b1bdeb`（单 head），两库均跑通；`downgrade` 可回退；`alembic check` 报无差异
- [x] 改邮箱后历史数据全保留；`users.id` 全流程不变；`cd backend && pytest` 全绿 —— 287 passed / 1 skipped；新增 `tests/test_stable_user_id.py`（3 例）覆盖改邮箱后主键不变、业务数据保留、会话不失效
- [x] `GET /knowledge/subjects` 返回 9 学科 —— 实测 200 + 9 条（含各科 pointCount）；`scripts/seed_kb_subjects.py` 幂等补齐，本地库与 Neon 均已导入
- [x] 契约中不存在 /ocr；openapi.yaml 增量冻结（冻结后改动走变更流程）—— 契约升至 **v1.6.0**（51 paths / 145 schemas），`routes/ocr.py` 与 `main.py` 挂载已删，目标态 §3.5 文案同步
- [x] 匿名兜底在游客态设计中有明确结论（游客数据不落库不串号，见 A 板块）—— 结论写入契约 `info.description`：生产无会话一律 401，游客试用**不走后端接口**，A 板块不得新增「游客可写」接口

> **M0 附带修复（复验时发现，均属"Neon 方言差异"风险项）**：
> ① `auth_sessions.expires_at` / `auth_codes.expires_at` 存毫秒时间戳却是 `Integer`，SQLite 动态宽度掩盖了问题，**Postgres 上会溢出** → 改 `BigInteger`；
> ② `pyproject.toml` **没有任何 Postgres 驱动**，DATABASE_URL 指向 Neon 会直接报 `No module named 'psycopg2'` → 补 `psycopg2-binary`；
> ③ `auth_sessions` 由存 email 改存 user_id 时**必须重建表**（NOT NULL 新列无默认值 + SQLite DROP COLUMN 受限），代价是升级后需重新登录一次。

> **M0 补漏（2026-09-19，第二张迁移 `b81d83bafb89`）**：定稿时发现原 11 张表**未覆盖 M2+ 的硬需求**，若等各板块开工才发现，会撞上「Alembic 只有 X0 能写」的排期墙。已一次补齐 5 张表（表数 42 → 47）：
> - `timer_sessions` + `timer_segments`（**C·M2 地基**）—— §3.6/D30 要求服务端持久化进行中的计时会话，D31 僵尸治理与 #14 分段计时都挂在它上面；没有它，C 的验收门「刷新/断线按 mode 正确恢复」无法实现。
> - `analytics_events`（G·M6 / D39 三块埋点）。
> - `search_archives`（D·M3 / §3.8.4：搜题归档与讲解归档分开）。
> - `card_impressions`（E·M4 / D28：冷却与去重指纹的直接依据）。
>
> 契约同步升至 **162 schemas**；SQLite 与 Neon 均已升级，`downgrade` 与 `alembic check` 通过。字段设计依据与「为什么必须有」都写在各 model 与 schema 的 docstring/description 里，板块若认为字段不合适可在开工前提变更（pilot 删档期改表成本低）。

### M1 · 地基：身份与 Chat 内核（A + B 核心 + G-usage_ledger + X1 壳初版）

范围：
- A：邀请码注册（一码一用）；激活式建档；游客态（D1/D43，叠加在现有 401 事件机制上，**不重写**）；监护人授权归位设置-授权与隐私（D41）；#29b 提升体验开关 opt-in；监护人确认结果页（现状 confirm 只返回裸 JSON，无前端页）。
- B：**新建 `routes/chat.py`**——Chat 真链路（意图管道：斜杠/按钮/裸判三通道）；单对话+上下文栈（D2/D36）；不做对话历史（D45，含原文 TTL 清除 job）；画像存储与四组结构（D50）；情绪安全 L1/L2/L3（D37）；#17 防破甲三层；#24 中学解法 prompt 基线；D3/D25 意图注册；#34 话题摘要（冷启动注入）。
- G（提前项）：usage_ledger 写入挂 LLM provider 出口——**必须在 Chat 首次真实调用前生效**。
- X1：首页 Chat 布局初版（问候语骨架+对话流+侧面板位+推荐卡位）；D22 卡片协议组件；D17 锚定确认卡组件。
- 同时执行：**Chat mock 页下架**（已拍板：/chat 入口下线，不再保留演示标）。

验收门：
- [ ] 注册→建档→（低龄）监护人授权→首页 Chat 全链路可走通
- [ ] Chat 一轮对话真实调用 LLM 且 usage_ledger 有对应数值流水；AICallLog 仍无身份
- [ ] UI 上不存在历史列表/新建对话；上下文栈深度=3 实测
- [ ] 游客可试用非 AI 功能且全程无写入；游客→登录后试用数据清空
- [ ] 危机词触发转介；事件细节不入画像（测试断言）
- [ ] 画像四组可按意图选组注入（日志可证）；无"新建画像"入口
- [ ] pytest 全绿 + 新增契约测试通过

### M2 · 主闭环迁移（C + B 增强 + X1 响应式起步）

范围：
- C：计划→计时→记录在新 IA 下跑通（D4 任务卡、D14/D15 自评双轨、D16 锚定回溯、D20 收尾三层、D30–D32 双模式与僵尸治理、#14 分段计时）；目标树父子（D6/D29）；**Exam 实体**（D49：成绩回填喂状态评估与画像）；D5 计时侧栏受限 Chat（调 B 接口）。
- B 增强：D51 划选两条路径（主对话引用 + 随手问浮窗）；D23 自定义常用语；#20 语言风格；D53 多产物。
- X1：`/study-timer` 刷新丢上下文修复（改 planId 自取）；移动端响应式起步（Chat/计时两页）。

验收门：
- [ ] 首日闭环（计划→计时→记录→状态+建议）在新壳内完成，无旧页依赖
- [ ] 计时刷新/断线按 mode 正确恢复；僵尸会话不产生记录
- [ ] 记录可事后回写正确率/错题且不触发重复评估
- [ ] Exam 创建→Goal 引用→成绩回填→评估联动走通
- [ ] 浮窗单向继承、不递归、关闭销毁；入主对话只带显式内容

### M3 · 知识与题本（D）

范围：知识页八合一（D8/D27，删 KNOWLEDGE_TREE 假树）；题本升格（D48，错因+意图，返考叫「复习/小测」）；搜题三态（D24）；讲解与呈现（D52：回顾取原文+重讲现生成、精品样例 3–5 个、多解法分页≤3、原文回溯、查词卡片）；难度双层（D13）；知识资产归位（D47 的 D 侧）；错题向量走本地模型（合规口径，与知识库智谱 API 链路分开）。

验收门：
- [ ] 题本两正交维度可用；mastery 只消费有错因的；推断添加必过确认卡
- [ ] 搜题三态可切换且被记忆；结尾统一知识点卡；解法不超纲
- [ ] 精品样例入库可检索，与动态生成可区分
- [ ] 知识页无假树；检索/详情/图谱用真数据
- [ ] 错题 embedding 全程不出域（egress 测试断言）

### M4 · 个人中心与收藏社区（E + X1 容器）

范围：个人中心容器（数据/画像管理/档案/复盘记录/目标树详情/社区参照/收藏/设置）；收藏体系（D46 快照、#41 虚化持久化、#52 覆盖+轻提示、#47 归位 E 侧）；社区 L1–L4（D9/D12/D18/D19/D33/D35，**前端接真 aggregate，localStorage 假人与 CommunityDemoBadge 下线**）；推荐卡三组与生成规则（D21/D28）；复盘侧面板+记录（D7）；设置瘦身收尾（D42 E 侧：权重调参 UI 下线）。

验收门：
- [ ] /personal-data、/summary-review、/recommendations、/goals 按迁移清单处置，无 404
- [ ] 收藏在原文过期后仍完整可读（快照）；虚化状态持久化
- [ ] 社区页所有数值来自真接口；pool<k 时无数值；L4 标注三要素默认收起
- [ ] 设置页不再出现引擎调参 UI
- [ ] 推荐卡冷却规则实测（3天/7天/周1）

### M5 · 多模态与工具（F）

范围：首个 UploadFile 通道（D55/#21/#47：限页数大小、仅会话内、不落库；要点摘要进收藏走 privacy_filter）；学科工具顶栏（D56，X1 配合壳）；科学计算器（D57，添加到对话注入全部 history 含未求值）；/题目排序（D58 四选项含价值遴选）；作业单照片直接生成计划。

验收门：
- [ ] 文件关会话即不可访问；不落库（存储扫描断言）
- [ ] 摘要入库前脱敏（测试）
- [ ] 计算器 history 含未按"="的表达式；注入变输入框引用块
- [ ] 题目排序四选项可用；首次光效引导仅出现一次

### M6 · 治理收尾与 pilot 验收（G + X2）

范围：只读用量页（D38/#7，无支付入口）；报错入口两处（#46）；违规分级处置+留痕（#43）；奖章最小版（#49）；埋点三块（D39）；pilot 核心指标与阶段准入成文（#53）；协议与条款（#29a，上线前补项）；X2 发布验收（契约测试/权限测试/E2E/降级矩阵/性能预算）。

验收门：
- [ ] 每次真实模型调用可追溯到用户数值成本；用量页只读
- [ ] 消息级报错带上下文；违规处置日志完整
- [ ] pilot 指标可从埋点直接读出
- [ ] 全量 pytest + 契约测试 + egress CI 全绿；降级矩阵每条有实测记录

## 5. 四档清单（严格分开）

| 档 | 内容 |
|---|---|
| **pilot 必做** | M0–M4 全部 + M5 科学计算器与上传通道 + M6 核心（usage_ledger/报错/违规/指标） |
| **二期** | D26 L3 富交互（🟡）、#25 文件内圈选、#18b 收藏导出、#44 课时排序、D33 前瞻轨迹精细版、R2 对象存储 |
| **beta** | 原生 App、不删档迁移方案、支付评估启动 |
| **支付后置** | #30 渠道选型、充值页、付费协议条款（pilot 结束后） |

## 6. 风险与回退

| 风险 | 影响 | 对策 |
|---|---|---|
| Chat 真链路（M1）延期 | 全项目核心，阻塞 F/影响 E | M1 只锁定**最小真链路**（单轮问答+意图管道+栈），划选/常用语已挪 M2；再不行砍 D23 |
| 稳定 ID 改造波及测试 | 8 个测试文件用 X-User-ID 头 | 新 ID 保持 `u_` 前缀兼容；X0 先改 conftest 再改实现 |
| 板块并行改同一共享文件 | 合并冲突 | 共享文件独占表（contracts §5）；App.jsx/类型/样式/迁移只有指定人动 |
| Neon 方言差异 | 空库自举在 Postgres 失败 | M0 内复验，不过夜 |
| 画像提取质量不可控 | D50 信任基础设施失信 | pilot 先**显式字段**（设置/建档/自评），模型推断一律走确认卡 |
| localStorage 双写清理误删用户数据 | ErrorBook/Chat 面板历史数据 | pilot 删档口径下可清；清理前在迁移清单逐项确认 |
| 多 agent 契约漂移 | 接口不一致 | openapi.yaml 变更走 PR + X0 评审；契约测试进 CI 守门 |

## 7. 验收门总表（go/no-go）

| 门 | 判据 |
|---|---|
| M0→M1 | 空库自举双库通过；学科接口有数；契约冻结；pytest 绿 |
| M1→M2 | Chat 真链路+usage_ledger 流水；游客态无写入；无历史 UI；测试绿 |
| M2→M3 | 首日闭环新壳跑通；Exam 联动；计时恢复正确 |
| M3→M4 | 题本两维度；搜题三态；错题不出域断言 |
| M4→M5 | 四旧页处置无 404；社区真数据；收藏快照可读 |
| M5→M6 | 文件不落库断言；计算器注入完整 |
| M6→pilot 发布 | 指标可读；全测试绿；协议条款可读；降级矩阵实测 |

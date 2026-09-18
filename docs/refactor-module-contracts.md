# 板块契约（所有权 · 协议 · 禁止越界）

> 版本：v1.0 · 2026-09-18
> 用途：多人 / 多 agent 并行的**边界法**。每个板块一张卡：你拥有什么、你对外提供什么、你不许碰什么。
> 主计划见 [refactor-development-plan.md](./refactor-development-plan.md)；决策归属见 [refactor-decision-mapping.md](./refactor-decision-mapping.md)。

---

## 0. 协作铁律

1. **契约先行**：新字段/新实体/新接口先改 `docs/openapi.yaml`，过 X0 评审，再写实现。
2. **Alembic 只有 X0 能写**——任何板块需要表结构变更，提需求给 X0，不自写迁移（防多 head 重演）。
3. **共享文件唯一编辑者**（见 §5 表）：`App.jsx`、`types/api.ts`、全局样式、package manifest、Alembic versions。其他人提 PR 由独占者合并。
4. **跨板块只走协议**：实体引用或本文 §3 的三个协议；**不允许读别人的内部状态、不许跨板块直连别人的表**。
5. 组件不直接 fetch，统一走 `frontend/src/services/`；服务文件按 openapi tag 命名，消灭 V2/复数并存。
6. 每完成一项：`pytest` 绿 → `npm run typecheck` → 更新对应文档。**跑测试不会清开发库**（`4a2afea` 已隔离），但不要在测试外手动清 `data.db` / `kb_vectors/`。
7. 工作区存在多人未提交内容（README/.gitignore/新 docs/Neon 配置/.workbuddy-ai/）——**禁止 reset、clean、覆盖、删除**。

---

## 1. 板块卡

### X0 · 契约与数据平台

| 项 | 内容 |
|---|---|
| 职责 | openapi.yaml 唯一维护；数据库实体与 Alembic；稳定 user_id；Neon；后台 jobs；横切安全三件套（egress_guard / privacy_filter / safety_filter）；prompt 基线文件 |
| 前端目录 | `frontend/src/types/api.ts`（与 X1 共管，X0 定字段 X1 管导出） |
| 后端 | `models/`、`alembic/`、`database.py`、`jobs/`、`egress_guard.py`、`privacy_filter.py`、`safety_filter.py`、`prompts/` |
| 表 | 全部 29 表现有 + 新实体 DDL（exams、collections、collection_items、usage_ledger、invite_codes、violation_logs、error_reports、medals、user_profiles、topic_summaries、explanations） |
| 测试 | `test_e2e_contract.py`、`test_egress_*.py`、`test_deploy_config.py`、迁移自举测试 |
| 对外提供 | 冻结的契约；共享 schema；安全三件套 API；kb_subjects 9 行数据 |
| 依赖 | 无（最先启动） |
| 禁止 | 不写任何业务路由逻辑；不动前端页面 |

### A · 身份、入口与合规

| 项 | 内容 |
|---|---|
| 职责 | 注册登录、邀请码、激活式建档、游客态、监护人授权、授权与隐私子页、协议条款、账号生命周期 |
| 前端目录 | `pages/Login/Register/ForgotPassword`（根级三文件）、`pages/ProfileSetup/`、`pages/GuardianAuth/`（并入设置）、`pages/Settings/` 的授权与隐私子页、游客态身份区组件 |
| 后端 | `routes/auth.py`、`routes/user.py`（/me、guardian 系列）、`auth/` 包 |
| 表 | auth_users、auth_codes、auth_sessions、users、settings、guardian_authorizations、invite_codes（新，DDL 归 X0） |
| 服务层 | `services/authApi.js`、`user.ts`、`guardian.ts`、`settings.ts` |
| 测试 | `test_auth*.py`、`test_me_and_guardian.py`、`test_email_mock.py` |
| 对外提供 | 会话校验（deps.current_user 语义）、游客态判定 API、授权状态查询（供 E 的社区开关校验、D41） |
| 依赖 | X0（稳定 ID、invite_codes 表） |
| 禁止 | 不碰 Chat/画像；不在游客态写任何业务表；**不重写 401 事件机制**（`http.ts` + `epochx:auth-expired`），只叠加 |

### B · Chat 内核、记忆与画像

| 项 | 内容 |
|---|---|
| 职责 | Chat 真链路、意图管道、上下文栈、无历史设计、话题摘要、画像提取与按意图注入、语言风格、受限 Chat 两种配置（计时侧栏/随手问浮窗）、情绪安全响应 |
| 前端目录 | `pages/Chat/`（重写）、浮窗组件、引用块 UI、划选交互 |
| 后端 | **新建 `routes/chat.py`**、画像服务、话题摘要服务、原文 TTL 清除 job（jobs/ 下，调度归 X0 范式） |
| 表 | user_profiles（画像，新）、topic_summaries（新）、对话原文短期留存（新，TTL）；读：learning_records 等（只读，经 C 的接口或只读查询） |
| 服务层 | 新建 `services/chat.ts`、`profile.ts` |
| 测试 | 新建 `test_chat*.py`、`test_profile_injection.py`、情绪安全用例 |
| 对外提供 | **引用块协议**（§3.1，给 F/D/E）；**受限 Chat 接口**（给 C 计时侧栏）；画像注入 API（内部）；锚定确认卡消费方 |
| 依赖 | X0（契约/安全三件套/prompt 基线）、A（会话） |
| 禁止 | 不做历史列表/新建对话（D45 红线）；画像不可手动新建；动作类请求（加题本/改画像）不直接执行，一律出锚定确认卡 |

### C · 计划、目标、考试、计时与学习记录

| 项 | 内容 |
|---|---|
| 职责 | guide、任务卡、目标树、Exam、成绩回填、双模式计时、分段计时、收尾卡、锚定回溯、状态引擎联动 |
| 前端目录 | `pages/StudyGuide/`、`pages/StudyTimer/`、`pages/Goals/`（并入个人中心）、任务卡组件 |
| 后端 | `routes/plan.py`、`goal.py`、`learning_record.py`、`assessment.py`、`state_engine/`、`state_calculator.py`、新建 `routes/exam.py` |
| 表 | plans、plan_tasks、goals、learning_records、assessment_snapshots、exams（新，DDL 归 X0） |
| 服务层 | `plans.ts`、`goals.ts`、`learningRecord.ts`、`focus.ts`、`checkIn.ts`、`duration.ts` |
| 测试 | `test_assessment.py`、`test_scoring.py`、`test_weights.py`、`test_today_completed.py`、新建 `test_exam.py` |
| 对外提供 | 计划/任务/记录的锚定引用（§3.2，给 B/E）；计时恢复 API；Exam 数据源 |
| 依赖 | X0、A、B（受限 Chat 接口） |
| 禁止 | 不直接调 LLM（建议生成走现有 ai_suggestion 编排层）；不自建 Chat 侧栏逻辑，调 B 的受限配置 |

### D · 知识、题本与 AI 辅导

| 项 | 内容 |
|---|---|
| 职责 | 知识检索、mastery、题本（错因/意图）、搜题三态、多解法、原文回溯、讲解归档、精品讲解、相似题、复习小测 |
| 前端目录 | `pages/Knowledge/`（含 Graph）、`pages/ErrorBook/`（升为题本并入知识页）、搜题侧面板、讲解视图 |
| 后端 | `routes/knowledge_kb.py`、`error_book.py`（扩展题本）、`mastery.py`、`mastery_engine/`、`knowledge.py`（归因）、新建讲解/搜题路由；`embedding_service.py`、`vector_store.py` |
| 表 | kb_* 9 张（kb_errors 扩展错因/意图/来源考试字段）、explanations（新，DDL 归 X0） |
| 服务层 | `knowledge.ts`/`knowledgeV2.ts`（**合并归一**）、`errorBook.ts`、`mastery.ts`、`knowledgeSummary.ts` |
| 测试 | `test_knowledge*.py`、`test_mastery*.py`、`test_error_book.py`、`test_rag_retrieval.py`、`test_vector_store.py`、新建 `test_topic_book.py` |
| 对外提供 | **知识引用协议**（§3.3，给 F/B）；题本锚定（给 C 锚定回溯）；知识点卡数据 |
| 依赖 | X0（kb_subjects 数据、explanations 表）、B（意图管道） |
| 禁止 | **错题/学习记录 embedding 不出域**（本地模型，PRD 12.6）；知识库向量走智谱 API 是既定口径，两条链路不得混；不硬塞库外知识进 mastery |

### E · 个人中心、收藏、社区与设置

| 项 | 内容 |
|---|---|
| 职责 | 个人中心聚合、画像管理 UI、收藏快照（高亮/虚化/自定义分组）、复盘记录、社区 L1–L4、推荐卡三组与生成规则、设置（授权与隐私之外的部分） |
| 前端目录 | `pages/PersonalData/`（升为个人中心容器）、`pages/SummaryReview/`（并入）、`pages/Recommendations/`（并入首页）、收藏页、`pages/Community/`（接线改造）、`pages/Settings/`（授权与隐私之外） |
| 后端 | `routes/summary.py`、`recommendation.py`、`recommendation_content.py`、`daily_summary.py`、`community.py`、新建 `routes/collections.py` |
| 表 | summaries、recommendations、community_* 3 张、collections/collection_items（新，DDL 归 X0） |
| 服务层 | `summary.ts`/`summaries.ts`（**合并归一**）、`recommendations.ts`、`communityApi.ts`（已存在，扩）、新建 `collections.ts`；`utils/aggregate.ts`（统计后端化后下线，二期） |
| 测试 | `test_community_*.py`、新建 `test_collections.py`、推荐规则用例 |
| 对外提供 | 收藏快照读写 API（给 B 的收藏动作、F 的摘要进收藏）；社区参照数据；推荐卡数据（给 X1 首页） |
| 依赖 | X0、c（数据消费）、B（画像数据源） |
| 禁止 | 社区不做任何社交元素；pool<k 不渲染数值；**localStorage 假人必须随接线一并下线**，不留双轨 |

### F · 多模态、文件与学科工具

| 项 | 内容 |
|---|---|
| 职责 | 图片/PDF/PPT 上传、题面与手写内容确认、作业单生成计划、/题目排序、科学计算器、学科工具顶栏与浮窗 |
| 前端目录 | 新建 `pages/Tools/`（或组件目录）、上传组件、计算器组件、题目排序 UI |
| 后端 | 新建 `routes/upload.py`（**全仓第一个 UploadFile**）；文件解析服务（会话内，不落库） |
| 表 | 无（文件不落库）；消费 collections（经 E 的 API） |
| 服务层 | 新建 `upload.ts`、`tools.ts` |
| 测试 | 新建 `test_upload.py`（限页数/大小/不落库断言） |
| 对外提供 | 上传→引用块（走 B 的引用块协议）；作业单→计划（调 C 的计划接口） |
| 依赖 | **B 的引用块协议文本、D 的知识引用协议文本**（文本落定即可开工，不必等实现）；X0（限流与 egress 规则） |
| 禁止 | 文件不落库、不建 R2（二期）；不复活 OCR；图片圈选不做（二期） |

### G · pilot 运营与治理

| 项 | 内容 |
|---|---|
| 职责 | usage_ledger 计量、只读用量页、AI 质量反馈、用户报错两处、违规累计处置与封禁、奖章最小版、功能开关、pilot 指标 |
| 前端目录 | 设置内用量页、报错入口（设置常驻 + 消息级按钮）、奖章展示 |
| 后端 | usage_ledger 写入（挂 LLM provider 出口，`llm_provider.py`）、新建 `routes/governance.py`（报错/违规/奖章） |
| 表 | usage_ledger、violation_logs、error_reports、medals（均新，DDL 归 X0）；读 AICallLog（不改它） |
| 服务层 | 新建 `usage.ts`、`feedback.ts`（已有雏形，扩） |
| 测试 | 新建 `test_usage_ledger.py`、`test_violation.py` |
| 对外提供 | 用量查询 API；报错接收 API；违规处置 API |
| 依赖 | X0（表）；**usage_ledger 必须先于 B 首次真实调用**——这是全项目最硬的一条时序 |
| 禁止 | 不做支付/充值任何 UI；不做排行榜/积分商城；不给 AICallLog 补身份字段 |

### X1 · 前端壳与响应式

| 项 | 内容 |
|---|---|
| 职责 | 路由壳、首页 Chat 布局、个人中心容器、全局顶部学科工具壳、浮窗框架、移动端关键页、官网（`域/`）与应用（`域/app`）同域 |
| 前端目录 | `App.jsx`、`components/AppShell/`、`components/RequireAuth/`、`context/`、`styles/`（tokens/global）、首页布局组件、通用组件库（D17 锚定确认卡、D22 卡片协议） |
| 后端 | 无（配合 X0 的同域部署形态） |
| 表 | 无 |
| 服务层 | `services/http.ts`（401 机制维护者） |
| 测试 | `npm run typecheck`、构建、（X2 配合的）E2E |
| 对外提供 | 路由注册位、壳插槽（侧面板/推荐卡位/顶栏）、通用组件 |
| 依赖 | 各板块页面产出（最后收口） |
| 禁止 | 不改各板块页面内部逻辑；**UI 视觉风格未拍板，不得默认沿用液态玻璃**——壳先做结构，皮肤等设计拍板 |

### X2 · QA、安全与观测

| 项 | 内容 |
|---|---|
| 职责 | 契约测试、权限测试、跨模块 E2E、AI 安全、成本监控、性能预算、降级矩阵、发布验收 |
| 拥有 | `backend/tests/` 新增契约/权限用例、egress CI、E2E 脚本（playwright-core 复用系统 Edge 的套路已有，见 9/15 记忆） |
| 基线 | 现有 43 个测试文件全绿是必须守住的底线 |
| 对外提供 | 每个里程碑验收门的实测报告；降级矩阵 |
| 依赖 | 全程 |
| 禁止 | 不为了赶进度放行红测试；不修改业务代码让测试"碰巧过" |

---

## 2. 共享实体字典（新实体一览，DDL 全归 X0）

| 实体 | 关键字段（草案） | 主要消费方 | 对应决策 |
|---|---|---|---|
| exams | id、user_id、subject、name、exam_date、score、full_score | C | D49 |
| collections | id、user_id、name（自定义分组）、内置维度不入表（筛选用） | E | D46/D47 |
| collection_items | id、collection_id、**snapshot_json（快照）**、source_ref、highlight_json、blur_state、created_at | E（B/F 经 API 写入） | D46/#41/#52 |
| usage_ledger | id、user_id、feature_tier、model、tokens_in、tokens_out、cost、created_at（**只存数值**） | G | #9/D38 |
| invite_codes | code、used_by、used_at、note（一码一用） | A | #50 |
| violation_logs | id、user_id、level、action（warn/temp_ban/perm_ban）、reason、created_at | G | #43 |
| error_reports | id、user_id、message_id、intent、context_json、created_at | G | #46 |
| medals | id、user_id、milestone、awarded_at（3–5 个里程碑枚举） | G | #49 |
| user_profiles（画像） | user_id、group（学习/状态/归因/兴趣经历）、key、value、source、updated_at（可改可删、无手动新建） | B | D50 |
| topic_summaries | user_id、session_id、summary（2–3 条）、created_at | B | #34 |
| explanations（讲解归档） | id、user_id、point_id、mode（original/regenerated）、content、is_curated（精品标记） | D | D52/#22 |
| kb_errors 扩展 | +error_cause、+intent、+source_exam_id（三列加在现有表） | D | D48/D49 |

> 字段名为草案，**以 openapi.yaml 最终落定为准**。加列/新表一律 X0 出迁移。

## 3. 跨板块协议（文本先冻结，实现后跟进）

### 3.1 Chat 引用块协议（B 产出 → F/D/E 消费）

一条引用块 = `{ type, title, payload, display }`：
- `type`：`calculator`（F）/ `knowledge_point`（D）/ `plan_task`（C）/ `collection`（E）/ `file_summary`（F）
- `payload`：结构化数据（注入模型上下文用）；`display`：渲染数据
- 规则：添加到主对话**只带显式输入输出、不带隐式上下文**（D51/#45）；引用块可 ✕ 移除，移除即出上下文栈。

### 3.2 锚定与回溯协议（C 产出 → B/E 消费）

三级锚点：`plan → plan_task → learning_record`，外加 `exam`、`topic_book_item`（D 产出）。
- 任何结构化产物（复盘、建议、Chat 消息）可携带锚点 id；点击跳到对应实体视图。
- 锚定确认卡（D17，X1 组件）：所有"模型建议落库"的动作（加题本/改画像/建目标）必须经过它，确认才执行（#17 防破甲第三层）。

### 3.3 知识引用协议（D 产出 → F/B 消费）

知识点引用 = `{ pointId, subjectCode, name, mastery? }`。
- F 的题目排序（价值遴选）、B 的搜题意图路由、E 的收藏来源标注统一用此结构。
- 库外知识：只进画像归因，引用结构里 `pointId=null`，**不进 mastery**（#40b）。

## 4. 共享文件独占表

| 文件/目录 | 唯一编辑者 | 其他人怎么办 |
|---|---|---|
| `docs/openapi.yaml` | X0 | 提变更请求，X0 改+评审 |
| `backend/alembic/versions/` | X0 | 提 DDL 需求 |
| `backend/models/__init__.py` | X0 | 同上 |
| `frontend/src/App.jsx` | X1（集成者） | 板块提供页面组件与路由声明片段，X1 注册 |
| `frontend/src/types/api.ts` | X0 定字段 / X1 管导出 | 不动手 |
| `frontend/src/styles/global.css`、`tokens.css` | X1 | 页面级样式用 CSS Modules |
| `frontend/package.json`、`vite.config.ts` | X1 | 加依赖提 PR |
| `backend/main.py`（router 挂载） | X0 | 板块提供 router 文件，X0 挂载 |
| `frontend/src/services/http.ts` | X1 | 改 401/错误机制需 X1+X2 双确认 |
| `README.md`、根目录配置 | 集成者（Skyer 指定） | 不动 |

## 5. 分支与集成流程

1. 分支命名：`feat/refactor-identity`（A）、`feat/refactor-chat`（B）、`feat/refactor-learning-flow`（C）、`feat/refactor-knowledge`（D）、`feat/refactor-center`（E）、`feat/refactor-multimodal`（F）、`feat/refactor-governance`（G）、`feat/refactor-contracts`（X0）、`feat/refactor-shell`（X1）。
2. 顺序：X0 契约 PR 先合 → 各板块从最新 main 切出 → 完成后 X2 跑契约测试 → X1 收口共享入口 → 集成者合并。
3. 每个 PR 必须带：契约变更链接（如有）、pytest 截图、typecheck 结果、对应 D 编号。
4. 冲突裁决：契约问题 X0 说了算；壳与路由 X1 说了算；跨板块语义争议升级到 Skyer。
5. 当前分支 `fix-current-user-privilege-escalation` 的未提交内容（README/.gitignore/新 docs/Neon 配置）由集成者决定合入时机，各板块分支**不得基于这些未提交内容开发**（以 origin/main + X0 契约 PR 为基线）。

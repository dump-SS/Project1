# 面向大规模功能整合与 UI/UX 重构的结构化梳理

> 版本：v1.0 · 2026-09-11
> 基线：当前工作区代码（非旧文档）。所有结论均来自源码取证，文件路径可直接点击。
> 阅读对象：主导本轮整合/重构的同学。优先级口径：🔴 核心功能（主闭环不可缺）／🟡 辅助功能（增强或半落地）／🔵 实验性 PoC（mock、占位或未接线）。
> 契约铁律不变：字段/枚举/接口以 [openapi.yaml](./openapi.yaml) 为唯一真相。

---

## 一、功能清单（Feature Inventory）

### 0. 一句话理解数据如何在各功能间流动

**「学习记录」是全系统的数据枢纽**。几乎所有功能要么生产它，要么消费它：

```
StudyTimer(录入行为+自评) ──POST /learning-records──▶ DB
                                 │
        ┌────────────────────────┼─────────────────────────────┐
        ▼                        ▼                             ▼
 state_engine 评分/标签     Recommendation(pending)      各消费方：
 AssessmentSnapshot     →  ai_suggestion 后台 LLM/模板   · PersonalData 前端聚合
        │                        │                       · Summary 状态复盘
        ▼                        ▼                       · mastery 画像
 /assessments 状态标签     前端轮询 GET /{id}            · 板块三特征抽取 job
                                                         · 周复盘 job
```

- **计划（Plan/PlanTask）**：决定任务清单与完成率（completion），导学页生成、计时页消费、社区 job 统计。
- **错题（ErrorRecord）**：关联知识点后驱动 mastery、知识图谱、error-parse 归因、周复盘，并与 Chat 页共享本地数据。
- **设置三开关**：`aiWeightTuningEnabled` / `sendTextToAI` / `knowledgeAiEgressEnabled` 横切控制整条 AI 出域链路。

### 1. 认证与账户（后端 `auth/`、`routes/auth.py`；前端 Login/Register/ForgotPassword）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 邮箱注册（验证码 + 强密码） | 🔴 | 10 个 `/auth/*` 接口全在 FastAPI；依赖 `AuthUser/AuthCode/AuthSession` 三表 |
| 双因子登录（验证码 / 密码） | 🔴 | 失败锁定走 `auth/rate_limit.py`（进程内计数） |
| 找回密码（校验码不消费 → 重置） | 🔴 | SMTP 发信：`smtp_provider=real/mock`，mock 写日志 |
| 会话校验 `GET /auth/me` + 登出 | 🔴 | HttpOnly `sid` cookie；前端 [AuthContext.jsx](../frontend/src/context/AuthContext.jsx) 挂载时调一次 |
| 验证码 60s 频控 | 🟡 | 与登录失败锁定同一套内存计数器，**重启即失效** |
| dev-login 一键登录中间件 | 🔵 | 仅 Vite dev server（[vite.config.ts](../frontend/vite.config.ts)），生产构建不生效；默认落地页竟指向 `/chat` |

### 2. 资料建档与未成年人合规

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 资料建档（学段/年级/学科，PUT 幂等 + PATCH 局部） | 🔴 | [ProfileSetup](../frontend/src/pages/ProfileSetup/index.tsx)；未建档用户 `/me` 返回 `onboardingCompleted=false` 桩，前端据此引导 |
| 设置三开关 | 🔴 | [Settings](../frontend/src/pages/Settings/index.jsx)；直接决定 LLM 是否能收到文本/知识聚合特征 |
| 监护人授权（提交 → token 链接 → 确认/撤销/过期） | 🔴 | [GuardianAuth](../frontend/src/pages/GuardianAuth/index.tsx)；监护人**无账号**，持 token 访问 `/guardian-authorization/confirm`；14 岁以下另有独立规则（见 test_me_and_guardian） |
| 板块三匿名聚合授权（同意/撤回） | 🔴 | `/me/community-consent`；撤回触发 7 天内物理删除 + ≤24h 延迟重算 |
| 授权确认闭环按钮 | 🟡 | 当前后端把确认 token 返给前端拼链接（MVP 简化，非真发邮件） |

### 3. 板块一 · 导学与计划（默认落地页 `/study-guide`）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 当日计划生成/重生成（10–600 分钟） | 🔴 | `POST /plans`；逻辑集中在 [usePlanFlow.js](../frontend/src/hooks/usePlanFlow.js) |
| 计划任务勾选完成（PATCH task） | 🔴 | 完成率回流社区 completion 指标 |
| 计划列表/详情 | 🟡 | 按日期查当日计划并回填 |
| LLM 内容推荐 + AUTO 自动填充学科/主题 | 🟡 | `/recommendation-content`；service 层自带 localStorage 离线缓存 |
| 进入计时的过场（弹窗 → 黑场 → 水淹动画） | 🔵 | 纯展示，与业务耦合在 StudyGuide 的 stage 状态机里 |
| StudyPlanEditor 旧目录 | 🟡 | 页面已重定向，但 `StudyEditor.jsx/TaskList.jsx/EnterButton.jsx` 仍被 StudyGuide 复用，属「旧目录装新页面」 |

### 4. 板块一 · 专注计时（`/study-timer`）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 倒计时（路由 state 接收 minutes/task/subject/planId） | 🔴 | 依赖上一页 `navigate(state)`，**直接访问/刷新会丢上下文** |
| 结束提交学习记录（完成度/正确率/打断/失焦 + 专注/疲劳/情绪/难度） | 🔴 | 6 维自评 + 4 维行为，契约 `RecordInput`；提交即触发评估与建议 |
| 提交后查看建议并评分 | 🟡 | 注意：`getRecommendation` 被放在 `services/learningRecord` 里（跨资源） |

### 5. 板块一 · 个人数据总览（`/personal-data`，9 张卡片）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 打卡、时长、学科分布、专注/疲劳、日历热力、目标、状态分解、mastery、最新摘要 | 🔴 | 每卡片一个 service 文件（calendar/checkIn/duration/focus/goals/mastery/stateBreakdown/subjectDistribution/summary） |
| 三级取数降级 api → cache → placeholder | 🟡 | [usePanelData.ts](../frontend/src/hooks/usePanelData.ts)，占位不伪装真实数据（卡片角标标注来源） |
| 日/周/月聚合在前端计算 | 🟡 | [aggregate.ts](../frontend/src/utils/aggregate.ts)；通过 `apiGetAllPages` 50 条/页全量拉取后浏览器聚合 |

### 6. 板块一 · 建议与复盘

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 学习建议（记录提交自动触发 + 手动按学科请求） | 🔴 | pending 句柄 → 后台任务 → 前端轮询；[Recommendations](../frontend/src/pages/Recommendations/index.tsx) |
| 建议反馈（useful/neutral/not_useful） | 🟡 | |
| 状态复盘（3–31 天区间） | 🔴 | 数据不足 `insufficient_data`、失败 `failed`，不伪造内容（[SummaryReview](../frontend/src/pages/SummaryReview/index.tsx)） |
| 模板兜底 `source=template` | 🟡 | LLM 超时/解析失败时 [template_fallback.py](../backend/template_fallback.py) 兜底，建议永不 500 |
| 学科知识复盘（每日限 1 次，429 限流） | 🟡 | `/knowledge-summary`，202 异步 + dimension=knowledge |
| 自动周复盘 job（每日 03:00，本周记录 ≥3 触发） | 🟡 | [weekly_knowledge_summary.py](../backend/jobs/weekly_knowledge_summary.py)，进程内 asyncio 定时器 |

### 7. 目标管理（`/goals`）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 目标 CRUD、归档、终态 outcome（achieved/abandoned/expired） | 🔴 | 可关联知识点 `pointIds` |
| 目标卡片（个人数据页内嵌） | 🟡 | 同一份数据两处消费 |

### 8. 板块二 · 学科知识与错题

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 知识库 5 个只读接口（学科/知识点列表/详情/图谱/match） | 🔴 | [knowledge_kb.py](../backend/routes/knowledge_kb.py)；种子脚本在 `scripts/seed_kb_*.py`，目前内容偏示例 |
| mastery 掌握度引擎（五因子公式 + timeline，3 接口） | 🔴 | [mastery_engine/](../backend/mastery_engine/__init__.py)，纯计算、MIN_SAMPLES=3 置信度规则 |
| 错题本 CRUD + 软删 + 敏感词阻断 + 艾宾浩斯复习 | 🔴 | [error_book.py](../backend/routes/error_book.py)；前端 [ErrorBook](../frontend/src/pages/ErrorBook/index.tsx) **后端失败时双写 localStorage** |
| 知识图谱可视化（vis-network，掌握度色阶 + 点选联动） | 🟡 | [Graph.tsx](../frontend/src/pages/Knowledge/Graph.tsx) |
| 错题 AI 归因 `/error-parse`（合规 RAG 形态） | 🟡 | errorId 引用 + EgressGuard 白名单出域；**但 embedding 默认 off，实际走名称模糊匹配，RAG 未真正打通** |
| Embedding/FAISS 向量检索 | 🔵 | `kb_embed_mode=off`；[embedding_service.py](../backend/embedding_service.py) + [vector_store.py](../backend/vector_store.py) + 本地索引 `kb_vectors/` 已就位 |
| OCR 录题 | 🔵 | `routes/ocr.py` 仅 501 占位，手动录入保底 |
| Knowledge 页硬编码知识树 | 🔵 | [index.tsx](../frontend/src/pages/Knowledge/index.tsx) 内 `KNOWLEDGE_TREE` 与真实 API 数据并存（半成品迁移） |
| AI 辅导对话 `/chat` | 🔵 | **纯前端**：setTimeout 1.5s + 关键词匹配 mock（[mockData.ts](../frontend/src/pages/Chat/mockData.ts)），无任何后端接口；错题面板共享 localStorage 裸 key |

### 9. 板块三 · 匿名群体参照（前后端双轨、尚未接线）

| 功能 | 级别 | 说明与依赖 |
|---|---|---|
| 后端聚合查询 `/community/aggregate` | 🔴 | k=20 最小群体、不足时不返回任何数值；直方图桶 count<3 合并邻桶；分位数 p25/50/75 |
| 特征抽取 job（周日 23:59，ISO 周周期 upsert） | 🟡 | [community_extraction.py](../backend/jobs/community_extraction.py)，服务端抽取为唯一真源，HMAC 匿名 ID |
| 聚合 job（每日低峰全量重算，不够 k 即删旧行） | 🟡 | [jobs/community_aggregate.py](../backend/jobs/community_aggregate.py) |
| 前端上传/对比页 | 🔵 | **纯 localStorage**：首次写入 20 条预置假人，不调任何后端（[community.ts](../frontend/src/pages/Community/community.ts)）；外层套 `CommunityDemoBadge` 演示标 |

### 10. 横切基建（无页面但所有功能依赖）

| 功能 | 级别 | 说明 |
|---|---|---|
| 出域管控 EgressGuard（默认拒绝 + 白名单 + raw 黑名单） | 🔴 | [egress_guard.py](../backend/egress_guard.py)，CI 抓包测试守门 |
| 敏感信息脱敏（身份证/手机/邮箱/QQ） | 🔴 | [privacy_filter.py](../backend/privacy_filter.py)，入 prompt 前替换 |
| LLM 输出安全审核 + 危机信号应答 | 🔴 | [safety_filter.py](../backend/safety_filter.py) |
| AI 调用留痕 / 限流计数 | 🟡 | `ai_call_log.py` 写 `AICallLog`（写失败静默）；建议 5/日、复盘 1/日 |
| 侧边栏导航壳 + 路由守卫 | 🔴 | [AppShell](../frontend/src/components/AppShell/index.jsx) v0.4 左侧栏；[RequireAuth](../frontend/src/components/RequireAuth/index.jsx) |
| 日/夜双主题 | 🟡 | ThemeContext + tokens.css，0.6s 过渡 |
| 氛围组件（开屏/页面过渡/云层切换/自定义光标） | 🔵 | 展示层，重构时应与业务页面解耦评估 |

---

## 二、用户结构与信息架构（User & IA）

### 1. 用户角色

| 角色 | 真实存在？ | 标识与能力 |
|---|---|---|
| **学生（主用户）** | 是，唯一登录角色 | 邮箱注册；分 junior（初一~初三+其它）/ senior（高一~高三+其它）；所有业务功能 |
| **监护人** | 半存在（无账号、无登录） | 仅通过一次性 token 链接完成授权确认/查看撤销；没有任何页面入口 |
| **未建档新用户** | 是（一种状态） | 能登录，`onboardingCompleted=false`，应被引导至资料建档 |
| **14 岁以下学生** | 是（特殊分支） | 需监护人同意 + 独立处理规则（后端有专门测试） |
| **匿名/演示访客** | ⚠️ 后端事实上允许 | `current_user` 在无 sid 时**兜底为共享用户 `u_10237`**（见第三部分技术债 #1）；前端 RequireAuth 只是 UI 层守卫 |
| 管理员/教师/家长端 | 否 | 产品明确不做 |

### 2. 页面层级地图（Site Map）

```
公开层（无 AppShell）
├── /login · /register · /forgot-password
└── /guardian-authorization/confirm?token=…   （监护人，token 换态）

受保护层（RequireAuth → AppShell v0.4 侧边栏）
├── /  → 重定向 /study-guide
├── 板块一
│   ├── /study-guide        导学（默认落地页；/study-plan 重定向至此）
│   ├── /study-timer        专注计时
│   ├── /personal-data      个人数据（9 卡片纵排）
│   ├── /summary-review     复盘（状态复盘 / 知识复盘 双 tab）
│   ├── /recommendations    建议（状态建议 / 内容建议）
│   └── /goals              目标
├── 板块二
│   ├── /knowledge          学科知识库（列表/详情 + /Graph 图谱视图）
│   ├── /error-book         错题本（9 学科 tab）
│   └── /chat               AI 辅导（三栏，纯 mock）
├── 板块三（演示徽章）
│   └── /community/{upload,compare}
└── 「我的」分组
    ├── /settings           设置三开关 + 社区授权
    ├── /profile-setup      资料建档
    └── /guardian-auth      监护人授权
* 任何未匹配路由 → /login
```

导航实际呈现（与旧文档不同，以代码为准）：桌面侧栏 **10 个主项**（导学/计时/数据/复盘/建议/目标/学科/错题/AI辅导/群体）+「我的」3 项 + 底部主题/退出/折叠；移动端底部 tab **原样渲染这 10 项 + 「我的」= 11 个 tab**（必然拥挤，UI 重构必须解决）。

### 3. 关键用户路径（User Flows）

**流程 A：新用户首日（注册 → 合规 → 首个闭环）**
```
注册(邮箱验证码) → /auth/me 建立会话 → onboardingCompleted=false
→ 资料建档(学段/年级/学科) → [低龄]监护人授权 pending→active
→ 导学页生成当晚计划 → ENTER 过场 → /study-timer
→ 提交首条学习记录 → 生成评估快照 + 建议(pending→轮询)
→ 建议页查看/反馈 → 数据页看到首个数据点
```

**流程 B：每日学习闭环（产品主循环）**
```
导学页(回填当日计划/AUTO 推荐) → 计时 → 提交记录
  → 状态标签更新(/assessments，按学科不合并且)
  → 建议随状态变化 → 每 3–31 天发起状态复盘
  → 计划完成度反哺次日规划
```

**流程 C：错题驱动的学科闭环（板块二）**
```
错题本/Chat 面板录入错题 → 敏感词校验 → match 知识点(off 时模糊匹配)
→ mastery 五因子更新 → 图谱变色 / 数据页 mastery 卡片
→ 艾宾浩斯到期复习(记住了/没记住) → 周复盘 job 汇总 → 知识复盘
```

**流程 D：目标管理**：建档时关联学科/知识点 → 列表跟踪 → 终态 outcome + completionNote。

**流程 E：群体参照（当前是假路径）**：设置中授权 consent（真）→ 前端 upload/compare 仅写本机浏览器（假）⇄ 后端抽取/聚合 job 与 /community/aggregate 已真实运行，但**前端没有接**。

---

## 三、实现逻辑与重构提示（Logic & Refactor Hints）

### 1. 技术栈与核心第三方依赖

| 层 | 技术 | 备注 |
|---|---|---|
| 前端框架 | React 18 + Vite 5 + react-router-dom 6 | JSX 与 TSX 刻意共存；`@` 别名指向 src |
| UI/图表 | antd 5（ConfigProvider 页面级注入）、Recharts、vis-network、react-markdown、dayjs | 无统一组件库收口，登录/计时等页不使用 antd |
| 后端 | FastAPI 0.115、Pydantic v2、SQLAlchemy 2.0、SQLite | Python 3.12；camelCase 靠全局 `response_model_by_alias` |
| AI/检索 | OpenAI 兼容 LLM（httpx）、faiss-cpu、bge-small-zh（规划） | embedding 默认关闭 |
| 数据迁移 | Alembic（**仅留痕，禁止 upgrade head**） | schema 真相是 `Base.metadata.create_all` |
| 异步 | FastAPI BackgroundTasks + 进程内 asyncio 定时器 | 无 Celery/RQ，无多实例保护 |
| 认证 | 自管 session 表 + HttpOnly sid cookie | JWT 配置仍在但未用作主方案 |
| 测试 | pytest（145+ passed）、httpx | 含 egress CI 抓包断言 |

### 2. 数据流向与状态管理

**前端没有全局数据层库**（无 Redux/React-Query）。数据流是「Context 管壳 + 页面自管 + service 裸调」：

```
AuthContext ──/auth/me──► user/status（全应用唯一全局业务状态）
ThemeContext ───────────► theme（localStorage 持久化）
页面组件 ──useState 自管──► services/*.ts ──http.ts(fetch, credentials:include)
                                      │
                                      ├─ 成功：渲染；PersonalData 额外写 panel 缓存
                                      ├─ 失败：ErrorBook/Chat/计划 → localStorage 兜底
                                      └       其余页面 → 就地错误文案/占位角标
轮询：建议/复盘页手写 setInterval 轮 GET /{id} 直到 status 终态
```

**后端写路径（以提交学习记录为例）**：

```
POST /learning-records
 → routes 层鉴权(current_user) + Pydantic 校验 + 落库
 → state_calculator（ORM↔引擎输入↔契约 dict）
 → state_engine 纯函数（评分/滑窗趋势/标签/权重硬限制）
 → 写 AssessmentSnapshot + 建 Recommendation(pending)
 → BackgroundTasks: ai_suggestion 自开 Session
     读设置开关 → 组装上下文 → privacy_filter 脱敏
     → EgressGuard.validate（默认拒绝）→ LLM provider
     → safety_filter 审核输出 → 成功写 ready / 失败写 template / 复盘写 failed
 → 前端轮询同一 id 拿终态
```

**板块三离线链路**：

```
consent 授权用户
 → 周日 23:59 抽取 job：learning_records + plan_tasks → community_features（白名单 4 指标）
 → 每日聚合 job：metric×stage 分位数+直方图，pool<k 删行 → community_aggregates 物化
 → GET /community/aggregate：k 值 + 限流（5 次/分钟）+ 数值裁剪后才出域
```

### 3. 模块职责边界与耦合度

| 单元 | 职责 | 耦合度评价 |
|---|---|---|
| `state_engine/` | 纯计算、零 IO | ✅ 边界最干净，重构时应原样保留 |
| `mastery_engine/` | 纯计算 | ✅ 同上 |
| `routes/` | HTTP/鉴权/落库 | ⚠️ plan.py 358 行、knowledge.py 333 行偏重，编排逻辑应下沉 |
| `state_calculator.py` / `ai_suggestion.py` | 编排层 | ✅ 分层正确；ai_suggestion 575 行偏大，建议/复盘/知识复盘三条链可再拆 |
| `auth/` | 认证子域，自成一包 | ✅ 独立清晰 |
| `services/`（前端） | 接口封装 | ⚠️ 碎片化：同资源多文件、跨资源函数乱放（见技术债 #5） |
| `usePanelData` | 取数降级范式 | ✅ 模式好，但只服务 PersonalData；全仓轮询/缓存各页手写 |
| `AppShell` | 导航壳 | ⚠️ 内含 ~170 行内联 SVG 图标 switch，导航项与移动端可用性绑死 |
| Chat 页群 | AI 对话 | 🔴 与错题本通过 localStorage 裸 key 隐式耦合，无 API 契约 |
| Community 前端 | 群体对比 | 🔴 与后端同名能力完全双轨，数据模型各写一套（前端 hours 0–40、四学科） |
| 样式 | tokens.css / global.css 液态玻璃类 / CSS Modules / antd token | ⚠️ 四套机制并存，主题切换靠 `[data-theme]` 属性 + 硬编码混用风险 |

### 4. ⚠️ 技术债、重复代码与反模式（按重构优先级排序）

| # | 问题 | 证据 | 影响 / 重构提示 |
|---|---|---|---|
| 1 | **业务接口匿名兜底为共享用户** | [deps.py](../backend/routes/deps.py#L92-L94)：无 sid 时 `user_id = "u_10237"`；还兼容 `X-User-ID` 头与 `Bearer u_` | 🔴 安全 + 数据串号：前端守卫可被绕过，所有未带 cookie 的调用读写同一人数据。整合前必须先定鉴权策略（401 还是演示模式显式开关） |
| 2 | **Chat 是纯 mock 却占一级导航，dev-login 默认跳它** | [Chat/index.tsx](../frontend/src/pages/Chat/index.tsx#L9-L11)；vite.config 默认 `to=/chat` | 🔴 演示与真实功能在 IA 上同权。重构需决定：接线真实对话接口，还是降级入口 |
| 3 | **板块三前后端双轨未接线** | 前端 community.ts 明文「不调任何后端」；后端 aggregate/consent/两个 job 均已实现 | 🟠 两套数据模型将来必然对齐，越晚越痛；建议本轮要么接线要么从主导航下架 |
| 4 | **错题双写逻辑写在页面组件里** | [ErrorBook/index.tsx](../frontend/src/pages/ErrorBook/index.tsx)（643 行）含 localStorage read/write；Chat 的 ErrorEntryPanel 也写同一裸 key | 🟠 数据分裂、组件承担存储职责。应下沉为 service 层单一数据源，删除裸 key 共享 |
| 5 | **service 层碎片化 / 跨资源** | 同资源两文件：`summary.ts`（复盘页用）与 `summaries.ts`（数据卡片用）；`knowledge.ts`（AI 归因）与 `knowledgeV2.ts`（知识库）；`learningRecord.ts` 里导出 `getRecommendation` | 🟡 整合时以 openapi tag 为准归一命名，消灭 V2/复数并存 |
| 6 | **枚举常量多处重定义且互相不一致** | SUBJECTS 散见于 ProfileSetup/Recommendations/Goals(取 theme)/Chat(9 科)/Community(4 科)；StudyTimer 自带 FOCUS/FATIGUE_LABELS | 🟡 学科集合应从 `types/api` 单点导出（契约唯一真相），标签走统一 i18n/字典 |
| 7 | **Knowledge 页硬编码假树与真 API 并存** | `KNOWLEDGE_TREE` 与 `fetchKnowledgePoints` 同页 | 🟡 典型半迁移状态，UI 重构时极易误删真链路；先删假数据 |
| 8 | **统计在前端、全量分页拉取** | aggregate.ts + `apiGetAllPages`（50/页，上限 200 页） | 🟡 数据量增长后流量/性能差；后端补统计接口后整体替换（README 已自认） |
| 9 | **无数据获取库，轮询/缓存/重试全手写** | 各页 setTimeout/setInterval；plans、recommendationContent 各自 localStorage 缓存 | 🟡 建议借重构引入 React-Query/SWR 统一异步态、去重、轮询、离线缓存 |
| 10 | **移动端导航 11 tab 必溢出** | AppShell 直接 map 10 个 PRIMARY_NAV + 我的 | 🟡 IA 重构硬约束：主次分组、更多菜单或底部 4–5 项 |
| 11 | **embedding/RAG 名实不符** | 默认 off；error-parse「向量 Top-5」实为名称模糊；OCR 501；mastery 周期调权未接 | 🟡 UI 文案不得宣称 AI 归因/拍题；功能整合需先给开关与降级矩阵 |
| 12 | **AI 调权运行时长期未生效** | weight_tuning.py（空库/缺表/模板兜底三因素，项目已知教训） | 🟡 设置页却提供「AI 自动调权」开关——避免给用户假控制感 |
| 13 | **异步与定时任务单机化** | BackgroundTasks 无队列/并发去重；两个 job 靠 startup asyncio，多实例会重复执行 | 🟡 pilot 可接受，扩规模前需任务队列 + 分布式锁 |
| 14 | **退役代码仍在仓** | mock-server 整目录；`mock_data.py` 210 行仅测试引用；根目录 `smoke_test_postfix.py` 游离 | 🟢 建议随重构删除/归档，降低新人认知负担 |
| 15 | **同名文件职责混淆** | `community_aggregate.py`（纯函数）vs `jobs/community_aggregate.py`（调度）；`ai_call_log.py`（写入器）vs `models/ai_call_log.py`（ORM）；`daily_summary.py` vs `routes/daily_summary.py` | 🟢 非重复但命名误导，建议加 `services/` 或改后缀区分 |
| 16 | **文档与代码漂移** | README 写「顶栏 6 导航」（实际侧栏 10 项）；backend README 称 goal/plan/user 仍读 mock_data（已不实）、接口数 29（契约 51 路径/65 路由声明） | 🟢 重构同步修文档，避免后人被误导 |
| 17 | **CORS 配置无效且不安全** | main.py `allow_origins=["*"]` + `allow_credentials=True` | 🟢 浏览器会拒绝该组合下的凭证；生产需白名单 |
| 18 | **样式四轨 + 页面自带 CSS 双文件** | Goals 引 index.css + App.css；多页全局 css 与 module css 混用 | 🟡 借设计系统重构收敛到 tokens + Modules，全局类仅留液态玻璃基类 |
| 19 | **计时页依赖路由 state** | 刷新/直链丢失 minutes/task/planId | 🟡 应以 planId 为参数自取计划，支持中断恢复 |
| 20 | **JWT/session 三套身份入口残留** | sid / X-User-ID / Bearer u_ 并存 | 🟢 收敛为 session 单一入口，调试通道显式环境隔离 |

### 5. 建议的重构推进顺序（步步为营）

1. **先立安全与数据基线**：处理 #1 鉴权兜底、#17 CORS；冻结契约 openapi.yaml。
2. **再做功能去伪**：Chat / Community / Knowledge 假树 / OCR / 调权开关逐一定性（接线或下架），同步修正文案与导航（#2/#3/#7/#10/#11/#12）。
3. **前端数据层归一**：抽统一异步层（轮询/缓存/降级），并 service（#5/#8/#9），错题存储收口（#4），枚举单点化（#6）。
4. **IA 与设计系统重构**：导航分组与移动端方案先行，再逐页换肤；样式四轨收敛（#10/#18）。
5. **后端瘦身**：大路由文件编排下沉、同名模块改名、删退役代码、修文档（#14/#15/#16）。
6. **规模化预埋**：embedding 启用决策、任务队列/分布式锁（#11/#13）。

> 每一步都应满足：契约先改 → 后端改 → 测试绿（`cd backend && .venv/Scripts/python -m pytest tests/ -q`）→ 前端接线 → typecheck/build → 更新对应文档。

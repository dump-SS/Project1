# 前端接线现状（frontend wiring status）

- **目的**：全站前端页面「数据从哪来」的唯一引用源。后续所有「某页面接没接」的派单、销项、验收以本文档为准，省掉当场 grep。
- **基线**：main `7212bd4`（chore(deploy): Railway 部署配置）；扫描含工作区未跟踪文件的长期存在不影响结论（只读）。
- **方法与规矩**（lead-2 立的三条，本文全遵守）：①路径类扫描一律绝对路径，结论注明 cwd；②任何否定式结论附三件套（确切命令 / 执行时 cwd / 扫描计数）；③断言「后端无 X」先过三关（ls backend/routes/ → APIRouter(prefix=...) → main.py include_router）。
- **维护约定**：pilot 放号 + 前端埋点接线（§5 第 2 项）后复跑库侧；B 板块 `chat.py` 落地后复跑 /chat；新页面接线后补行。见文末「复跑触发条件」。
- 评审人：dev-3（zcode）· 日期：2026-10-05 · 初版（待 lead-2 验收）

## 一、总览

| 路由 | 守卫 | 页面组件 | 消费的 services | 数据性质 | 诚实标注 |
|---|---|---|---|---|---|
| `/` | 公开 | Landing | **零** | 纯本地（营销页，无数据需求） | 不适用 |
| `/docs/*` | 公开 | Docs | **零** | 纯本地（内容打包于 registry，by design） | 不适用 |
| `/login` | 公开 | LoginPage | authApi | 真接口（/auth/* 10 端点） | — |
| `/register` | 公开 | RegisterPage | authApi | 真接口 | — |
| `/forgot-password` | 公开 | ForgotPasswordPage | authApi | 真接口 | — |
| `/study-guide` | 游客 | StudyGuide | plans、recommendationContent、http | 真接口 | — |
| `/study-timer` | 游客 | StudyTimer | **timer（6 网络函数+2 纯函数）**、plans、learningRecord、feedback | 真接口（GuestTimer 子组件纯本地=游客态设计） | 游客态用户主动进入，显式 |
| `/personal-data` | 需登录 | PersonalData | calendar、checkIn、duration、feedback、focus、goals、learningRecord、mastery、stateBreakdown、subjectDistribution、summaries（12 个，经 9 张卡） | **降级链**（usePanelData：api→cache→placeholder） | ✅ 合规（SectionCard「占位数据/缓存数据」徽标+Tooltip） |
| `/goals` | 需登录 | Goals | goals、exams（仅 listExams）、knowledgeV2、http | 真接口 | — |
| `/settings` | 需登录 | SettingsPage | settings、user、usage、guardian、feedback、communityApi、http | 真接口（数据流未变：GET/PATCH /me/settings，组件内无 fetch） | **改后状态已更新**（2026-10-05 dev-1：SWITCH_ITEMS +`userContentEmbeddingApiEnabled`(needsConsent)、新组件 UserContentEmbeddingConsent(antd Modal)、5 个 token-only class；三处重复 setValues 收成 toSettingsValues；**types/api.ts 的 Settings/SettingsUpdate 尚无该字段**——共享文件，已报 lead-2 派补） |
| `/summary-review` | 需登录 | SummaryReview | summary、knowledgeSummary | 真接口 | — |
| `/recommendations` | 需登录 | Recommendations | recommendations（全套+2s 轮询） | 真接口 | — |
| `/profile-setup` | 需登录 | ProfileSetup | user | 真接口 | — |
| `/guardian-auth` | 需登录 | GuardianAuth | **零** | **真实路由**（非路由级重定向）；页面组件内部 `Navigate` → `/settings?tab=privacy`（index.tsx:16，保留路由兼容旧链接）；本体归 Settings 授权与隐私 | 不适用 |
| `/knowledge` | 需登录 | Knowledge | knowledgeV2、mastery | 真接口（检索有降级，见 §4-2） | 见 §4-2 |
| `/error-book` | 需登录 | ErrorBook | errorBook、knowledge | 真接口 | — |
| `/chat` | 需登录 | Chat | **零** | **纯本地 mock**（setTimeout+关键词匹配+mockData.ts；文件头自述「纯前端演示，无后端」；B 板块未开工） | 文件头有自述；UI 可见演示徽标未逐项核实 |
| `/community/upload` | 需登录 | Community/Upload | communityApi、http | 真接口 | — |
| `/community/compare` | 需登录 | Community/Compare | communityApi、user、http | 真接口 | — |
| `/study-plan` | — | — | 路由级重定向 → `/study-guide` | — | — |
| `/community` | — | — | 路由级重定向 → `/community/upload` | — | — |

路由级口径：**19 页 + 2 路由级重定向**（/study-plan、/community，见 App.jsx L88/L103）；另有**组件级重定向** 1 处（/guardian-auth 页面内 Navigate，App.jsx:99 是真实路由）——两者不要混计。
| `/guardian-auth` 之外的第 3 个重定向 | — | — | `/settings?tab=privacy`（guardian-auth 归位，D41） | — | — |

RequireAuth 包裹 11 页（personal-data/goals/settings/summary-review/recommendations/profile-setup/guardian-auth/knowledge/error-book/chat/community/upload+compare）；未登录访问弹回 `/login` 并记住原路径（401 链路已闭环）。

## 二、services 层孤儿扫描（30 文件 · 三件套见文末）

**结论：0 个完整孤儿**（每个 service 文件至少有一个导出被页面/组件消费）；19 个文件导出全被引用；11 个文件含部分未引用导出，逐一定性如下（「跨 service 复用」= 被其他 services/\*.ts 消费，不算孤儿）：

| 文件 | 未被页面/组件直接引用的导出 | 定性 |
|---|---|---|
| `exams.ts` | createExam / deleteExam / getExam / updateExam / examScoreRate | **接线点**：Goals 页只消费 listExams（考试下拉）；考试 CRUD 前端接线是 C 板块剩余项 |
| `feedback.ts` | postAnalyticsEvent | **接线点 = §5 第 2 项「前端埋点接线」**（已知销项：`POST /analytics/events` 后端已通、前端零调用） |
| `learningRecord.ts` | createLearningRecord / listLearningRecords / deleteLearningRecord | **存疑**：StudyTimer 只用 updateLearningRecord（需要一个已存在的 recordId）——记录的**创建**路径当前无前端调用方，recordId 从哪来需查证 |
| `mastery.ts` | fetchSubjectMastery | 接线点（timeline 已接，单点掌握未接） |
| `knowledgeV2.ts` | fetchKnowledgePoint（单点）/ fetchKnowledgeSubjects | 接线点（列表与 graph 已接） |
| `timer.ts` | getTimerSession（详情端点） | 其余 6 网络函数 + 2 纯函数全部被 StudyTimer 消费（lead-2 逐行核证）——详情端点未接属小项 |
| `guestSession.ts` | buildGuestPlan / exitGuestMode / guestPlanStore | **跨 service 复用**：被 `services/plans.ts` 游客态消费——非孤儿 |
| `http.ts` | apiPatch / apiPut / apiGetAllPages | **跨 service 复用**：被各 service 消费——非孤儿 |
| `guardian.ts` | confirmGuardianAuthorization | **存疑**：授权确认流程已归位（GuardianAuth 页=重定向，本体在 Settings 的 GuardianAuthorizationPanel），confirm 单端点的前端消费方待查证 |
| `usage.ts` | getMyViolations | 接线点（usage/medals 已接，violation 面板未做——G 板块范畴） |
| `errorBook.ts` | fetchErrorRecord（详情端点） | 接线点（列表/创建/更新/复盘已接） |

## 三、已定事实引用（lead-2 提供，本文直接采用不再复核）

1. **部署形态**：前后端分离——前端 Vercel（epochx.net）、后端 Railway（api.epochx.net）。「同域单服务」不再是目标态。
2. **embedding 本地模式现状**：`pyproject.toml` 无 sentence-transformers / torch（仅 faiss-cpu）→ `embedding_service` local 模式必然 ImportError → 兜底返回 None → 降级 `name_fuzzy`。**本地与 Railway 容器当前都无本地向量能力**——凡涉及检索/向量的页面（/knowledge 等）按此口径记。
3. **Settings 用户内容 embedding 开关已落地**（2026-10-05 dev-1 交回，只改 pages/Settings 两个文件）：SWITCH_ITEMS +`userContentEmbeddingApiEnabled`（needsConsent）、新组件 UserContentEmbeddingConsent（antd Modal）、5 个 token-only CSS class、三处重复 setValues 收成 toSettingsValues helper；数据流未变（GET/PATCH `/me/settings`）。**残留**：`types/api.ts` 的 Settings/SettingsUpdate 尚无该字段（共享文件，已报 lead-2 派补）。
4. **已知契约-代码漂移（dev-1 核报 2026-10-05，非其引入，待 X0）**：① `Error.code` 在契约里是自由字符串无枚举，权威错误码清单在 `docs/archive/api-design-unified.md`（归档，非契约）；② 共享 response `GuardianAuthorizationRequired` 契约零引用（/me/settings 的 403 是内联重写）；③ `User.subjects` 后端 max_length=9 而契约无 maxItems、UserProfilePut/Patch 为 maxItems:10；④ `User.birth_year` 后端缺契约的 ge=1900/le=2100。

## 四、更正记录（本清单前身报告的误判，留痕防再犯）

| 轮次 | 误判 | 根因 | 修正 |
|---|---|---|---|
| 1 | C 板块体检报「/timer-sessions 后端零实现」 | grep 的 shell cwd 静默停在 `frontend/`，`os.walk('backend')` 扫了**不存在的路径得 0 个文件**，「扫了 0 个」被当成「扫了没命中」 | lead-1 核出 `routes/timer.py`（495 行）后，绝对路径复核并撤销 |
| 2 | 修订时报「services/timer.ts 前端未接（产品决策）」 | **多行 import 块**被单行正则漏配（StudyTimer L12-19 的块级导入） | lead-2 逐行核证六个网络函数全在用；扫描改块级解析 |
| 3 | 契约枚举审计报「ErrorCause.careless 6 值 vs 5 值待 X0 定」 | 只提取 enum 值、**没读 description**（L5016-5018 明写 careless 为历史兼容值） | lead-1 裁定保留 6 值；审计已修订 |

## 五、复跑触发条件

1. **pilot 放号 + 前端埋点接线（§5 第 2 项）完成后**——复跑库侧取值与 postAnalyticsEvent 接线状态（本清单 B 类最大项）
2. **B 板块 `routes/chat.py` 落地后**——/chat 从纯本地 mock 转真接口，整行重写
3. **C 板块后端 /timer-sessions 之外的新端点落地后**——对应 services 接线状态更新
4. **Settings 开关（dev-1）交回后**——本版已补「改后状态」；`types/api.ts` 字段补齐（lead-2 派）后再更新一次
5. 新页面路由注册后——补行

## 六、§5 第 4 项销项口径（2026-10-05 lead-2 定）

**「四页接真接口 + /timer-sessions 前后端均已实现且前端全量消费，无剩余缺口；『受限 Chat 侧栏』随 B 板块一并排期」**——勿让后来人以为受限 Chat 也已做了。

## 扫描三件套样例（本次主扫描）

- 命令：`os.walk` 绝对路径遍历 `frontend/src`（排除 node_modules）+ 多行 import 块正则（`import[\s\S]*?from '...'`）+ `@/` 别名从 `frontend/src` 根解析（**初版解析器误从页面目录解析 `@/` 导入导致 personal-data 扫描漏 9 张卡，已修复**）
- cwd：`D:/Projects/Project1/frontend`（结论中所有相对路径以此为准；脚本内全部 ROOT 绝对路径拼接）
- 计数：services/ 30 文件；消费方语料 119 文件（src 除 services/）；per-page 扫描文件数见总览「扫描文件数」列（43/2/1/1/1/2/2/11/1/3/1/1/1/1/2/1/9/1/1）

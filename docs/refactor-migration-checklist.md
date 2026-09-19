# 迁移清单（现状 → 目标态 · 逐项处置）

> 版本：v1.0 · 2026-09-18 · 基线：HEAD `736461a` 实测（19 条前端路由 / 63 个后端接口方法 / 29 张表）
> 用途：每个现有资产的**保留 / 重定向 / 并入 / 删除 / 兼容**结论。执行时逐行打勾。
> 处置口径：pilot 删档测试——数据结构可激进重建，但「页面找不到」「功能突然消失」不允许，每个删除项都有替代去向。

---

## 1. 前端路由处置（19 条，实测自 `App.jsx:40-79`）

| 路由 | 现状 | 处置 | 去向 / 负责板块 | 里程碑 |
|---|---|---|---|---|
| `/login` `/register` `/forgot-password` | 可用 | **保留** | X1 视觉重塑（风格未拍板，先结构） | M1 |
| `/` | 重定向 `/study-guide` | **改** | 重定向到首页 Chat | X1 | M1 |
| `/study-guide` | 默认落地页 | **保留** | guide 独立页（D22 卡片协议接入） | C+X1 | M2 |
| `/study-plan` | 已重定向 `/study-guide` | **删除残留** | 旧目录组件评估（见 §4-6） | C | M2 |
| `/study-timer` | 可用，依赖路由 state | **保留+改** | 全屏沉浸 + 侧栏受限 Chat；planId 自取修复刷新丢失 | C | M2 |
| `/chat` | **纯前端 mock** | **下架后重建** | mock 页下线（已拍板）；真链路 Chat 升为首页 | B+X1 | M1 |
| `/personal-data` | 9 卡片可用 | **并入** | 个人中心容器（组件整体搬迁复用） | E+X1 | M4 |
| `/summary-review` | 双 tab 可用 | **并入** | 个人中心-复盘记录 + chat 侧面板复盘 | E | M4 |
| `/recommendations` | 可用 | **取消独立页** | 并入首页推荐组（D21） | E+X1 | M4 |
| `/goals` | 可用 | **取消独立页** | 并入个人中心-目标树（D6） | C+E | M2/M4 |
| `/knowledge` | 列表+图谱，假树并存 | **保留+扩展** | 八合一（掌握度/检索/详情/题本/归档/图谱/难度/考试） | D | M3 |
| `/error-book` | 真接口+localStorage 回退 | **并入** | 知识页-题本；旧路径重定向 `/knowledge?tab=topics` | D | M3 |
| `/settings` | 三开关+社区授权 | **保留+瘦身** | 授权与隐私子页（监护人/三开关/群体参照/#29b）归 A；其余归 E；权重调参 UI 下线 | A+E | M1/M4 |
| `/profile-setup` | 可用 | **保留+改** | 激活式引导流程（D40） | A | M1 |
| `/guardian-auth` | 可用（已真调 confirm） | **并入** | 设置-授权与隐私；旧路径重定向 | A | M1 |
| `/community` `/community/upload` | localStorage 假人 | **删除** | 客户端不上传（服务端抽取为唯一真源，M0 决议）；无替代页 | E | M4 |
| `/community/compare` | localStorage 假人 | **并入** | 个人中心-社区参照，接真 aggregate | E | M4 |
| `/guardian-authorization/confirm` | **前端无此页**（后端返回裸 JSON） | **新增** | 监护人确认结果页（成功/失败/已过期三态） | A | M1 |
| `*` | 重定向 `/login` | **保留** | — | X1 | M1 |

## 2. 后端接口处置（18 router / 63 方法）

| router | 方法数 | 处置 | 说明 | 里程碑 |
|---|---|---|---|---|
| `auth.py` | 10 | **保留+改** | 注册加邀请码校验（#50）；session 改存 user_id（D59） | M0/M1 |
| `user.py` | 8 | **保留+改** | users.id 语义切稳定 ID；guardian 系列不动 | M0 |
| `goal.py` | 4 | **保留+改** | 父子树（D6）+ examId 引用（D49） | M2 |
| `plan.py` | 4 | **保留** | 编排下沉到服务层属内部重构，不改签名 | M2 |
| `learning_record.py` | 3 | **保留+改** | 回写口径（D15：回写不重复触发评估） | M2 |
| `assessment.py` | 3 | **保留** | — | — |
| `recommendation.py` | 4 | **保留** | — | — |
| `recommendation_content.py` | 1 | **保留** | — | — |
| `summary.py` | 4 | **保留** | — | — |
| `daily_summary.py` | 1 | **保留** | — | — |
| `weight.py` | 3 | **保留接口** | 用户侧调参 UI 下线（D42）；接口留内部 | M4 |
| `knowledge.py` | 2 | **保留+改** | `/error-parse` 归因对齐题本错因字段（D48） | M3 |
| `knowledge_kb.py` | 5 | **保留** | M0 补 kb_subjects 后即可用 | M0 |
| `error_book.py` | 6 | **扩展为题本** | +错因/意图/来源考试（D48/D49） | M3 |
| `mastery.py` | 3 | **保留** | 只消费有错因的题（D48） | M3 |
| `community.py` | 3 | **保留** | 已真实现（M1–M5 转正），无需动 | — |
| `ocr.py` | 1 | **M0 删除** | 含 main.py 挂载；契约本无此路径 | M0 |
| `health.py` | 1 | **保留** | — | — |
| **新增** `chat.py` | — | B | Chat 真链路 + 受限 Chat 配置 | M1 |
| **新增** `exam.py` | — | C | Exam CRUD + 成绩回填 | M2 |
| **新增** `collections.py` | — | E | 收藏快照读写 | M4 |
| **新增** `upload.py` | — | F | 首个 UploadFile，不落库 | M5 |
| **新增** `governance.py` | — | G | 报错/违规/奖章/用量查询 | M6 |

## 3. 数据库表处置（29 张）

| 处置 | 表 |
|---|---|
| **保留不动** | assessment_snapshots、learning_records、plans、plan_tasks、summaries、recommendations、ai_call_logs（⚠️ 永不加身份字段）、rate_limit_counters、auth_rate_limits、user_weight_configs、weight_adjust_logs、community_features、community_aggregates、community_audit_logs、kb_points、kb_point_relations、kb_point_mastery、kb_review_logs、kb_embeddings、auth_codes |
| **补数据** | kb_subjects（0 → 9 行，M0 硬前置） |
| **加列** | users（+email、+handle）、auth_users（+user_id）、kb_errors（+error_cause、+intent、+source_exam_id）、goals（父子树字段，X0 核对现有 schema 后定） |
| **改语义** | auth_sessions（存 user_id 不再存 email）、users.id（填稳定 ID 不再填 email） |
| **新建（11 张）** | exams、collections、collection_items、usage_ledger、invite_codes、violation_logs、error_reports、medals、user_profiles、topic_summaries、explanations（+ 对话原文短期留存表，B 定名） |

## 4. 功能去伪清单

| # | 假/旧功能 | 处置 | 里程碑 |
|---|---|---|---|
| 1 | Chat 纯 mock（setTimeout+mockData） | **下架**（已拍板），真链路替换 | M1 |
| 2 | Community localStorage 假人 + CommunityDemoBadge | 随真接口接线**一并下线**，不留双轨 | M4 |
| 3 | Knowledge 页 KNOWLEDGE_TREE 假树 | 删除，全真数据 | M3 |
| 4 | OCR 501 占位 | ✅ **已删**（M0：`routes/ocr.py` + `main.py` 挂载 + 目标态 §3.5 文案） | M0 |
| 5 | 设置页「AI 自动调权」开关 | 下线（避免假控制感，D42）；接口留内部 | M4 |
| 6 | StudyPlanEditor 旧目录 | 被 StudyGuide 复用的组件挪位保留，其余删 | M2 |
| 7 | `mock_data.py`（210 行，仅测试引用） | 测试改用工厂/fixtures 后删除 | M6 |
| 8 | mock-server 整目录 | 保留作历史参考（README 已注明），不动 | — |
| 9 | dev-login 中间件 | 保留（团队演示依赖）；确认落地页指向新首页 | M1 |

## 5. 数据策略（pilot 删档口径）

1. **稳定 ID 改造不做存量迁移脚本**：按新 schema 直接重建（D59 已授权）。
2. **知识库资产例外**：`kb_points` 3391 + `kb_point_relations` 3127 是导入资产——重建后用 `scripts/import_knowledge_points.py` 重灌（幂等已验证，约 21 分钟，走智谱 API）；`kb_subjects` 9 行写成独立 seed 一并执行。
3. **localStorage 双写数据**（ErrorBook / Chat ErrorEntryPanel 裸 key）：题本/收藏上线时**先读后删**——读逻辑确认无真接口数据遗漏后再移除 localStorage 路径；pilot 删档口径下允许直接清，但清理动作写进 PR 描述。
4. **对话原文短期留存**：TTL 清除 job（B 建、调度走 X0 范式），产品不可见，到期物理删。
5. **usage_ledger 上线前**的模型调用：AICallLog 照旧（无身份），不补历史账。

## 6. 兼容与回退

| 机制 | 策略 |
|---|---|
| 401 事件链（`epochx:auth-expired`） | **保留不重写**；游客态在其上叠加 |
| ErrorBook localStorage 回退 | 题本上线后随 #3 一并移除，先读后删 |
| openapi.yaml 变更 | 增量式，禁破坏性改字段名；必须破坏时走 X0 评审 + 双方同步 PR |
| 每里程碑 | main 打 tag（`m0`…`m6`）；验收门不过回退到上一 tag |
| 测试基线 | 43 个测试文件全绿是底线；新功能只增不破；改语义的测试（如 X-User-ID）由 X0 统一改 conftest |

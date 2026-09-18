# 现状盘点复核（对 refactor-2026-09-feature-ia-logic.md 的逐条标记）

> 复核时间：2026-09-18 · 复核基线：HEAD `736461a`（fix-current-user-privilege-escalation 分支）
> 用途：refactor-2026-09-feature-ia-logic.md（v1.0，2026-09-11 基线）的勘误附录。原文件**不改**，以本文为准。
> 方法：全部结论来自当前源码实测（路由装饰器统计、模型 `__tablename__`、openapi.yaml、前端源码、`.env` 开关），非复述文档。

## 一、HEAD 实测快照

| 项 | 实测值 |
|---|---|
| 后端 router | 18 个（`main.py:156-175` 挂载），约 63 个 endpoint 方法 |
| 数据库表 | 29 张（`models/*.py` + `auth/models.py` 的 `__tablename__`） |
| Alembic | 单基线 `1a6f0c6bb285`（29 表 / 53 索引 / down_revision=None），旧 14 个 revision 已归档 `versions_archive/` |
| openapi.yaml | v1.5.0，51 paths，**`x-status` 标记已全部移除** |
| 前端路由 | 19 条（`App.jsx:40-79`），页面目录 17 个 + 3 个根级 auth 页面文件 |
| 后端测试 | 43 个测试文件 |

## 二、已过时的条目（原盘点需修正）

| # | 原盘点说法 | 现状（实测） | 证据 |
|---|---|---|---|
| 1 | §1「失败锁定走 `auth/rate_limit.py` 进程内计数，重启失效」 | **已持久化**：`auth_rate_limits` 表，跨重启仍生效（`4f9c644`） | `models/rate_limit.py` |
| 2 | §2「授权确认闭环按钮 🟡：后端把 token 返给前端拼链接」 | 前端**已真实调用 confirm** 并刷新状态（`a4e27c9`）；剩余缺口仅为"非真发邮件"（MVP 简化，该半句仍准确） | `routes/user.py` 阶段 3 注释；GuardianAuth 页面 |
| 3 | §8「Embedding/FAISS 🔵 `kb_embed_mode=off`」 | `.env` 实测 `KB_EMBED_MODE=api`（智谱 embedding-3），3391 条知识点已向量化（9/7 导入）；FAISS 索引 ~27.7MB | `backend/.env`、`scripts/import_knowledge_points.py` |
| 4 | §8「错题本：后端失败时**双写** localStorage」+ 技术债 #4 | 已改为**真接口优先、失败回退 localStorage**（`9174939`，录入/列表走真接口）。Chat 的 ErrorEntryPanel 写 localStorage 裸 key 仍在 | `pages/ErrorBook/index.tsx` |
| 5 | §8「知识库内容偏示例」 | `kb_points` 3391 行 / `kb_point_relations` 3127 行，真数据。但 **`kb_subjects` 0 行** → `GET /knowledge/subjects` 读 `enabled=true` 的该表，**实测必返空**（implementation notes §10 待查项就此闭环：学科走表，不硬编码，**必须补 9 行学科数据**） | `routes/knowledge_kb.py:69-98` |
| 6 | §9 + README「板块三 3 条接口 501 预留（x-status: planned）」 | **已转正实现**（`d0d3f54` M1–M5）：`/community/aggregate` + `/me/community-consent` 真实运行；`/community/features` 按 M0 决议**废弃**（服务端抽取为唯一真源），契约里已不存在 | `openapi.yaml:2352` 注释、`routes/community.py` |
| 7 | §三.1「Alembic 仅留痕，禁止 upgrade head」 | **已反转**：squash 基线后空库 `upgrade head` 可自举，与开发库逐列 0 差异（`736461a`）；且 `models/__init__.py` 的 import 即 create_all 副作用已摘除 | `backend/README.md`、`alembic/env.py` |
| 8 | 技术债 #1「匿名兜底共享用户 u_10237 + X-User-ID」 | **已修复**（`98045d1`）：只认有效 sid，三层回落收进 `ALLOW_INSECURE_USER_HEADER`（默认 false，仅测试开启） | `routes/deps.py`、`config.py` |
| 9 | 技术债 #17「CORS 配置无效且不安全」 | **已修复**（`09f2f71`）：默认不挂 CORS 中间件（同域），分域走 `CORS_ALLOW_ORIGINS` 白名单；Cookie Secure/SameSite 按部署形态可配 | `main.py`、`auth/session.py` |
| 10 | 技术债 #20「JWT/session 三套身份入口并存」 | 部分过时：sid / X-User-ID / Bearer u_ 代码仍在，但后两者已被开关门控默认关闭（同 #8） | `routes/deps.py` |

## 三、仍准确的条目（复核确认）

| # | 条目 | 实测确认 |
|---|---|---|
| 1 | **Chat 是纯前端 mock**（setTimeout + 关键词匹配），后端无任何 chat 路由，却占一级导航 | `pages/Chat/index.tsx:28,71`；18 个 router 无 chat |
| 2 | **板块三前端双轨**：`pages/Community/community.ts` 纯 localStorage + 20 条假人，不调后端（后端已真实现，双轨差距更大） | community.ts 实测：localStorage=True、fetch=False |
| 3 | Knowledge 页硬编码 `KNOWLEDGE_TREE` 假树与真 API 并存（技术债 #7） | `pages/Knowledge/index.tsx` 仍含该常量 |
| 4 | OCR 501 占位（`routes/ocr.py`，1 个 POST）——契约里**没有** /ocr 路径，属"后端有占位、契约未收编"；implementation notes §8 已定可删 | `ocr.py` 501 标记仍在 |
| 5 | 数据枢纽图（学习记录是全系统枢纽）、用户角色、站点地图、四条关键用户路径 | 路由与页面结构未变 |
| 6 | 技术债 #3/#5/#6/#8/#9/#10/#12/#13/#14/#15/#16/#18/#19（服务碎片化、枚举多处、前端聚合、无数据层、11 tab、调权开关假控制、单机任务、退役代码、同名混淆、文档漂移、样式四轨、计时路由 state） | 无相关修复提交 |
| 7 | AI 出域横切链（EgressGuard / privacy_filter / safety_filter）为真 | 文件与测试均在 |

## 四、复核新发现（原盘点未覆盖）

1. **401 链路已闭环**（`6fe35c1`）：`http.ts` 拦 `UNAUTHENTICATED` → 广播 `epochx:auth-expired` → RequireAuth 弹回登录并记住原路径。重构时**不要重写这套**，游客态改造要在其上叠加。
2. **测试环境已隔离**（`4a2afea`）：pytest 走 `backend/.pytest_data/`，不再碰开发库与真实索引。这条是协作硬前提——任何 agent 跑测试都不会再清库。
3. **Neon 已接入**：根目录 `neon.ts`（空策略）+ `.env.local`（真实连接串，已 gitignore），项目 `EpochX/soft-moon-43682197`，分支 `production`。Postgres 方言复验未做（squash 只在 SQLite 验过）。
4. **dev-login 演示账号已恢复**（`demo@epochx.local`），vite 中间件硬编码依赖它。
5. **合规口径提醒**：知识点向量走智谱 API 是**既定决策**（知识库内容非用户数据）；错题/学习记录 embedding 必须走本地模型（PRD 12.6，knowledge_raw 不出域）。方案里两条链路要分开写。

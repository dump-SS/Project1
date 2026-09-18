# 全仓「空界面 / 假功能 / 占位实现」盘点

- 版本：v1.0
- 日期：2026-08-29
- 范围：`frontend/`、`backend/`、`docs/openapi.yaml` 契约比对；**板块三（/community 演示页与 3 条 planned 接口）不在本文**，其现状与计划见 `module3-development-plan.md`
- 分类口径：**A** = 完全未实现 / 假功能；**B** = 有真实实现但默认关闭或需配置才生效；**C** = 故意的降级兜底（正常设计，列出备查）
- 方法：全仓代码扫描 + 契约逐条比对 + 关键指控人工抽查复核（监护人 token 不返回、匿名回落 mock 用户两处已与代码核实）

---

## 0. 总览

| 类别 | 数量 | 一句话 |
|---|---|---|
| A 假功能 / 未实现 | 4 | Chat 页整体是演示壳；监护人确认闭环走不通；契约两条 GET 无实现 |
| B 默认关闭 / 需配置 | 6 | 代码是真的，默认部署下全部空转——演示前必须核对配置 |
| C 故意降级兜底 | 7 | 正常设计；其中匿名回落 mock 用户上线前必须移除 |
| 附带发现 | 3 | 文档腐化、SPA 回退吞 404、mock-server 已退役 |

---

## 1. A 级：真·假功能

### A1 Chat 页 AI 回复全部为前端 mock

- **位置**：`frontend/src/pages/Chat/mockData.ts:1-76`（`pickMockReply` 关键词匹配 4 条写死回复 + 默认句）、`frontend/src/pages/Chat/index.tsx:28,57,71`（setTimeout 1.5s 后追加 mock 回复）
- **现状**：不调用任何后端接口，回复池写死（复合函数 / 错题解析 / 计划 / 数列求和）。回复文案自带「这是演示模式」标注，属明示的假功能，但功能本身完全未实现。
- **建议**：接入后端对话接口前，页面只能定位为演示壳；若短期不接，保留「演示模式」标注即可，但 A2 必须先修。

### A2 Chat 页错题录入只写 localStorage，不进后端

- **位置**：`frontend/src/components/Chat/ErrorEntryPanel.tsx:4,17,62`（`writeErrors(...)` 直接写 localStorage `errors_{subject}`）
- **现状**：与错题本页共享 localStorage key，但从不调 `POST /error-book`。在 Chat 录入的错题不进库；错题本页优先读后端，后端有数据时这些本地条目直接不可见——**同一用户在两个页面看到不一致的错题本**。
- **建议**：Chat 错题录入改走 `services/errorBook.ts` 的真接口（低成本，接口已就绪），消除两页数据分裂。
- 附：Chat「我的错题」引用面板（`ReferencePanel.tsx:3,53`）读 localStorage，依附本条。

### A3 监护人授权确认闭环走不通，前端本地假装成功 ⚠ 合规相关

- **位置**：后端 `backend/routes/user.py:159-191`；前端 `frontend/src/pages/GuardianAuth/index.tsx:157-166`（`handleSimulateConfirm` 本地 `setStatus('active')` 模拟确认，刷新后失效）
- **现状**：`POST /me/guardian-authorization` 落库 GuardianAuthorization（pending + token），但**返回 202 空体**——注释写「MVP 阶段不真发邮件，token 直接返回」，代码却并没有返回 token，也不发邮件。token 无任何送达通道，正常用户无法完成确认；真实的 `GET /guardian-authorization/confirm?token=` 端点存在且可用，只是拿不到 token。**后端注释与代码行为不一致。**
- **影响**：监护人授权是 PRD 8.1 的合规底线功能，也是板块二/三多项能力的联动开关（授权失效时写接口 403、communityConsent 联动关闭）。当前只能靠前端演示按钮造假。
- **建议**（二选一）：① 开发期把 token 随 202 响应返回给前端（与注释承诺一致），演示链路即通；② 接 SMTP 真实发邮件（见 B6）。推荐先做 ①。

### A4 契约两条 GET `/knowledge-summary` 无后端实现

- **位置**：契约 `docs/openapi.yaml:2158`（列表）、`:2194`（详情）；后端 `backend/routes/knowledge.py` 仅有 POST（:142）与 POST /error-parse（:235）
- **现状**：契约定义了知识复盘列表/详情查询，后端未实现；前端也未调用（复盘列表实际走 `/summaries`），属契约超前。
- **附带坑**：未匹配的 `/api/v1/*` GET 会被 `main.py:173` 的 SPA catch-all 返回 index.html（200 + HTML），调用方拿到的不是 404 而是网页，排障时极易误判。
- **建议**：① 实现两条 GET（从 `summaries` 表按 `dimension='knowledge'` 过滤即可，成本低）；或 ② 契约降级标注。同时建议 SPA 回退只对非 `/api` 路径生效。

---

## 2. B 级：真实实现但默认配置下空转

> 共同点：**代码都是真的，默认部署下不生效**。演示或验收前逐项核对配置即可，不需要改代码。

| # | 功能 | 默认状态 | 开启方式 |
|---|---|---|---|
| B1 | 错题知识点向量匹配 | `kb_embed_mode="off"`（`backend/config.py:42`），永远走关键词降级；`backend/kb_vectors/` 为空 | 填 `embed_api_key/base_url/model`，切 `api`（智谱 embedding-3 联调已验证 4/4 命中，见 `module2-next-iteration-tasks.md` §7） |
| B2 | 知识图谱内容 | 代码真实（`knowledge_kb.py` graph 接口查 `KnowledgePointRelationORM`），未种子时图为空 | 跑 `scripts/seed_kb_math.py` / `seed_kb_physics_english.py` |
| B3 | LLM 生成（建议 / 复盘 / 导学推荐） | `llm_provider="mock"`（`config.py:35`），MockProvider 永远返回 None → 全部走规则模板（`template_fallback.py`、`KNOWLEDGE_SUMMARY_FALLBACK`） | 填 `llm_api_key/base_url/model`，`llm_provider` 切真实供应商。这是故意的多层兜底架构，但默认部署下没有任何真实 AI 输出 |
| B4 | AI 调权 | 触发链路真实（`learning_record.py:35,205` 提交记录后 BackgroundTasks + `weight.py:131 /tune-now` 手动端点），但因 B3 空转，调权永不执行只留日志。另：PRD 说「每周离线批量」，实际为事件驱动，无独立定时调度 | 随 B3 一并生效；是否补独立调度为产品决策 |
| B5 | 周复盘定时任务 | 调度真实（`main.py:34-45` lifespan 注册 asyncio 定时器，每日 03:00 + 启动即跑），但默认产出为模板复盘且 `data_record_count=0` | 随 B3 生效 |
| B6 | 验证码邮件 | `smtp_provider="real"` 但 `smtp_user/smtp_pass` 默认为空（`config.py:51-56`），发送必败 | 配 SMTP 账号，或团队测试走 mock |

---

## 3. C 级：故意的降级兜底（正常设计）

| # | 项 | 位置 | 备注 |
|---|---|---|---|
| C1 | OCR 录入占位 | `backend/routes/ocr.py:40-54` | 返回 200 + `available=false` 引导手动录入（ADR 记录的故意降级）。**小瑕疵**：docstring 声称返回 501 与实际行为不符；未入契约；前端无任何调用方，是死端点 |
| C2 | ErrorBook localStorage 兜底 | `pages/ErrorBook/index.tsx:118-153` | 后端不可达时降级，注释明写「演示兼容，不静默」。与 A2 联动会产生「Chat 录入只在本地」的假象 |
| C3 | Knowledge 页硬编码知识树兜底 | `pages/Knowledge/index.tsx:5,27-60` | 接口失败时保留 UI 不白屏。**无「演示数据」标注**，不如 PersonalData 的占位徽章规范 |
| C4 | 导学推荐数据量阈值占位 | `routes/recommendation_content.py:38,47` | 近 7 天 <3 条记录 `eligible=false`，PRD 冷启动设计 |
| C5 | PersonalData 占位体系 | `hooks/usePanelData.ts` + 各 service placeholder | 三级降级（实时→缓存→占位+徽章），「不要静默 mock」的规范设计 |
| C6 | localStorage 缓存兜底 | `services/plans.ts:30-43`、`recommendationContent.ts:30-42`、`localFallback.ts` | 网络不可达时回退上次成功数据 |
| C7 | **匿名访问回落到固定 mock 用户** | `backend/routes/deps.py:91-94` | 无登录态时 `user_id="u_10237"`，MVP 故意允许匿名访问，所有匿名数据挂在同一演示用户下。**上线前必须移除** |

---

## 4. 附带发现

1. **文档腐化**：`backend/README.md:18` 声称「goal / plan / user 仍读 mock_data.py」、`:62` 称 mock_data 为「阶段 2 硬编码假数据」；`backend/main.py:4-8,51-54` 的「阶段 2：所有路由接 mock 数据」注释同样过时。实际全部已落库，`mock_data.py` 仅被 `tests/test_smoke.py:16` 引用做 schema 校验。
2. **SPA 回退吞 404**：`main.py:173` catch-all 对未匹配 `/api/v1/*` GET 返回 index.html（见 A4）。
3. **mock-server 已退役**：`frontend/vite.config.ts:10` 注释确认；`backend/routes/auth.py` 已接管 auth；`mock-server/` 不再被任何活代码引用。

---

## 5. 演示 / 验收前检查清单

- [ ] B1：`KB_EMBED_MODE=api` + 智谱 key 生效，错题录入知识点建议走向量 Top-5
- [ ] B2：种子脚本已跑，图谱有节点和边
- [ ] B3：`llm_provider` 切真实供应商，建议/复盘出现非模板内容
- [ ] B4/B5：调权与周复盘随 B3 验证
- [ ] B6：SMTP 可发件（或确认演示走 mock 验证码）
- [ ] A3：监护人 token 有送达通道（先按建议 ① 改）
- [ ] A2：Chat 错题录入走真接口
- [ ] C7：确认演示环境允许匿名 mock 用户；上线前移除

## 6. 优先建议

1. **A3 监护人确认闭环**（合规底线，改动最小）：202 响应带 token，前端演示链路即通。
2. **A2 Chat 错题录入走真接口**：消除两页数据分裂。
3. **A4 两条 GET 实现或契约降级** + SPA 回退收窄到非 `/api` 路径。
4. B 级不涉及改代码，演示前按第 5 节清单配齐即可。

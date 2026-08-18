# Tasks

- [x] Task 1: 路由与目录骨架
  - [x] SubTask 1.1: 在 `frontend/src/pages/` 下新建 `Knowledge/` 与 `ErrorBook/` 两个目录
  - [x] SubTask 1.2: 在 `App.jsx` 注册 `/knowledge` 与 `/error-book` 两条路由，挂在 RequireAuth + AppShell 之下
  - [x] SubTask 1.3: AppShell 导航增加「学科」一级组（含「学科知识库」「错题本」两个二级项）

- [x] Task 2: 学科知识浏览页 `/knowledge`
  - [x] SubTask 2.1: 硬编码知识点树（数学 → 函数/几何/数列 → 叶子），含 `name / mastery / definition / errorTip`
  - [x] SubTask 2.2: 左侧 `Tree` 组件，节点右侧显示百分比与按阈值上色的色点（<40 红 / 40–70 橙 / >70 绿）
  - [x] SubTask 2.3: 右侧详情区（衬线体 24px 标题、定义、易错点、关联题灰色占位）
  - [x] SubTask 2.4: "查看概念图谱" 按钮触发 Modal "图谱功能将在 v2.3 上线"
  - [x] SubTask 2.5: 样式用 `styles/tokens.css` 的 `--font-serif` / `--r-card` / `--card-pad` / `--card-gap` 等变量

- [x] Task 3: 错题本工具与服务层
  - [x] SubTask 3.1: 新建 `utils/matchKnowledge.ts`，导出 `KNOWLEDGE_BASE` 与 `matchKnowledge(text)` 纯函数（含测试性 main-case 注释）
  - [x] SubTask 3.2: 新建 `services/knowledge.ts`，导出 `generateKnowledgeSummary(payload)` 与 `parseError(payload)`，走 `services/http.ts` 的 `apiPost`

- [x] Task 4: 错题本页 `/error-book`（基础版）
  - [x] SubTask 4.1: 学科 Tab（数学/物理/英语，默认数学）+ 录入区折叠面板
  - [x] SubTask 4.2: 录入表单（题目原文 TextArea / 错因 Select / 关联知识点 Select multiple / 保存按钮）
  - [x] SubTask 4.3: 保存到 `localStorage.errors_{subject}` 并刷新列表
  - [x] SubTask 4.4: 列表卡片（题目 2 行省略、错因标签按色、知识点标签淡蓝、相对时间、底部"生成复盘"按钮）
  - [x] SubTask 4.5: "生成复盘" 调 `services/knowledge.ts` 的 `generateKnowledgeSummary`，loading + 展开 + 失败 toast
  - [x] SubTask 4.6: 空状态（淡灰图标 + 引导文案 + 录入按钮）

- [x] Task 5: 错题本"搜题 + AI 解析"升级
  - [x] SubTask 5.1: 录入区加"题目关键词"输入 + "匹配知识点"按钮
  - [x] SubTask 5.2: 命中时显示匹配卡片（名称/掌握度色点/定义/易错点/确认关联按钮）
  - [x] SubTask 5.3: 未命中时显示全部知识点供手动选择
  - [x] SubTask 5.4: 错题卡片新增"AI 解析"按钮，调 `parseError`，loading + 展开 + 失败 toast
  - [x] SubTask 5.5: 保存错题时把"匹配到的"知识点自动填入关联字段（用户可改）

- [x] Task 6: 验证
  - [x] SubTask 6.1: `npm run build` 通过（tsc + vite build 无错误）
  - [x] SubTask 6.2: 启动 dev server，浏览器走 `/knowledge` 与 `/error-book` 两个流程，全部断言通过
  - [x] SubTask 6.3: 列表为空时显示空状态；保存一条后卡片出现；切换学科后列表切换
  - [x] SubTask 6.4: 后端未上线时，调用 `/api/knowledge-summary` 与 `/api/error-parse` 触发 toast 提示失败（不破版）

# Task Dependencies
- Task 4 depends on Task 3（依赖 utils / services）
- Task 5 depends on Task 4（在基础版之上扩展）
- Task 6 depends on Task 1–5

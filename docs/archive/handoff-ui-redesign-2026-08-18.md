# 交接文档 · EpochX 前端「人文风·空气感」UI 重设计

> **归档说明（2026-08-29 补记）**
>
> 本文档为历史快照，其阶段口径按当时的**正式发布尺度**书写（含「法务评审」「上线门硬前置」等要求），**不代表当前 pilot 口径，请勿据此安排工作**。
>
> 项目当前处于 pilot 阶段，由学生团队维持，无外部评审资源。现行阶段口径见仓库根目录 `PRD-学习状态智能助手.md` 文首「关于阶段口径」一节。

- 日期：2026-08-18
- 交接人：上一位 agent
- 一句话：设计规范 + 全站视觉皮肤 + 导航信息架构重构已完成并推送到 `origin/main`；当前正准备用「临时短路鉴权」让用户在浏览器里预览业务页，**这一步尚未执行**。

---

## 0. 立刻要接手的事（最高优先级）

用户上一条明确选择了「**临时短路鉴权**」，用于免登录预览业务页。**此改动我还没做**，请接手：

1. 编辑 `frontend/src/context/AuthContext.jsx` 的 `AuthProvider`：
   - `const [status, setStatus] = useState('checking')` → 改为 `useState('authenticated')`
   - `const [user, setUser] = useState(null)` → 改为 `useState({ email: 'preview@epochx.dev' })`
   - 注释掉挂载时的 `useEffect(() => { refresh() }, [refresh])`（否则 `/auth/me` 失败会把状态打回 `anonymous`）
   - **务必加醒目注释**（如 `⚠️ 临时视觉验证短路 —— 绝不提交！`）
2. dev server 已在后台跑（见 §3），HMR 会自动刷新，浏览器刷新后即可免登录进 `/study-guide`。
3. **这个改动绝对不能提交**。用户看完后立即 `git checkout -- frontend/src/context/AuthContext.jsx` 还原。
4. 还原后 `AuthContext.jsx` 会有一个未使用的 `useEffect` 导入——还原（checkout）会一并恢复，无需手动处理。

> 判断依据：当前 `AuthContext.jsx` 初值仍是 `useState('checking')`，短路残留检查=0，即短路**未生效**。

---

## 1. 项目背景

- 「学习状态智能助手 EpochX」板块一 MVP。三层结构：`frontend/`（Vite + React，`.jsx`/`.tsx` 共存）、`backend/`（FastAPI，:8000）、`mock-server/`（Node 邮箱认证，:4000）。
- 接口契约唯一权威：`docs/openapi.yaml`。前端写相对路径 `/api/v1/...`，dev server 代理到 `:4000`。
- 需求：`PRD-学习状态智能助手.md`（当前 v1.5，含板块二设计）。
- 登录后默认落地页：`/study-guide`（导学计划，是闭环入口）。

## 2. 本次已完成的工作（均已提交并推送到 origin/main）

设计方向「人文风·空气感」：天空渐变背景 + 磨砂玻璃卡 + 衬线标题 + 正文细体加粗 + 胶囊描边按钮 + 缓出动效。参考图是天空/云/海通透摄影。

规范文档：`docs/next-ui-redesign-spec.md`（v0.2）——含逐页盘点、起始页中央元素结论、设计令牌、多级菜单细则。

已推送的提交（`git log` 从新到旧）：
- `44a56ee` merge（含远端 PRD v1.4 #29）
- `0fb79cf` 导航信息架构重构：9 项平铺 → 4 组两级（今日/我的数据/目标/我的）+ 移动端底 Tab
- `796bf4c` 8 个业务页视觉铺开
- `c39dc51` 令牌基建 + 外壳 + 起始页 + 规范文档

关键实现点：
- **令牌单一真源**：`frontend/src/styles/tokens.css`（新增，`main.jsx` 先于 `global.css` 引入）。定义 `--sky-*` / `--cloud` / `--dusk-warm` / `--night-blue` / `--ink*` / `--primary*` / `--glass-*` / `--font-serif|sans` / 圆角/间距/动效令牌 + `.glass` 通用类 + `prefers-reduced-motion` 全局适配。
- **旧变量桥接**：`global.css` 的 `--color-*` 旧变量名保留、值指向 tokens.css 新令牌，所以大量用 `--color-*` 的页面（SummaryReview/Recommendations/ProfileSetup/GuardianAuth）自动切换了配色。
- **theme.ts**：色板同步空气感，**key 全不变**（antd ConfigProvider + Recharts 依赖），个人数据页 antd 组件随之统一。
- 各页 CSS 里的硬编码老浅蓝（`#4AD1FF`/`#7EC8E3`/`#009fff`/`rgba(74,209,255,...)` 等）已批量替换为新令牌色。
- 卡片统一磨砂玻璃（`backdrop-filter: blur(16px)` + `@supports not` 降级为半透实填）。
- 导航重构在 `AppShell/index.jsx`：`NAV_GROUPS` 分组结构，桌面 hover/focus 二级下拉，移动端（≤640px）底部 4 Tab + 二级抽屉。**路由路径与页面本身未变**。

## 3. 运行环境现状

- **后台 dev server 正在跑**：job id `bash-2`，`http://localhost:5173/`。用 `bash_output(job_id="bash-2")` 读输出，`kill_shell(job_id="bash-2")` 停止。
- mock-server（:4000）**未启动**，所以业务页数据接口会报 proxy error（各页有失败占位兜底，不影响视觉）。要走真实登录需 `cd mock-server; npm start`。
- 环境：Windows / PowerShell（不是 bash！`&&`/`||` 不解析，用 `;`）。node v24、npm 11。
- 验证命令（在 `frontend/` 下）：`npm run typecheck`（只查 .ts/.tsx）、`npm run build`（tsc -b && vite build）。最近一次均通过（2343 modules）。

## 4. git 状态

- 分支 `main`，与 `origin/main` 完全一致（HEAD = origin/main = `44a56ee`），工作区干净。
- ⚠️⚠️ **安全隐患**：`git remote -v` 显示 remote URL 里**明文内嵌了用户的 GitHub PAT**（`https://dump-SS:ghp_...@github.com/...`）。用户已在对话里贴过该 token。**强烈建议提醒用户吊销并重新生成该 PAT**，并把 remote 换回干净地址：`git remote set-url origin https://github.com/dump-SS/Project1.git`（不走网络，立即生效）。
- 网络注意：本机连 github.com 时通时断（443/22 都遇到过超时/重置），push/pull 可能需重试。

## 5. 还没做的事 / 可能的后续

- 起始页 Hero 目前用纯天空渐变，规范里提到「可叠低对比云摄影」，尚未加背景摄影图（需可商用素材，未选图）。
- 番茄钟中央的花体 `EpochX` 渐变已从紫改暖金；如需进一步调整仪式感可再议。
- 暗色模式：令牌已含 `--night-blue`，规范列为增量项，本期未做。
- 组件库是否全站统一到 antd：规范建议不强推（避免主题外溢到非 antd 的登录/番茄钟页），保持自定义 CSS 实现玻璃/胶囊。
- 全部改动均为**纯呈现层**，未碰组件逻辑/className 语义/service/接口/数据流。这条铁律请继续保持。

## 6. 关键约定（务必遵守）

- 只改呈现层，不动功能闭环、`openapi.yaml`、service、hooks 数据语义。
- 页面里禁止硬编码色值，一律引用 tokens.css / theme.ts 令牌。
- 标题衬线（`--font-serif`，500-600）、正文无衬线细体（350-400）、关键值加粗（600）。
- 用户交流用简体中文；代码/路径/命令保持原文。
- 提交前先 `npm run typecheck` + `npm run build`；main 分支 push 前跟用户确认。
- 临时短路鉴权（§0）绝不可提交。

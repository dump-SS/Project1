# 学习状态智能助手

板块一 MVP。仓库内是**一个** Vite 前端工程加一个本地服务，多人共用。

- 需求：`PRD-学习状态智能助手-v1.3.md`
- 接口契约：`docs/openapi.yaml`（唯一生效版本，字段名以此为准）

## 仓库结构（新加页面前请先读这一节）

```
frontend/          唯一的前端工程，所有页面都放这里，不要在别处再建一个
mock-server/       本地 Node 服务，:4000，目前提供邮箱认证接口
docs/              接口契约
```

**约定：新页面放 `frontend/src/pages/<PageName>/`，然后在 `frontend/src/App.jsx` 里注册路由。**

`.jsx` 和 `.tsx` 可以共存，Vite 的 React 插件原生支持，**不需要为了统一语言去改别人的代码**。
登录/注册/找回密码是 JavaScript，个人数据页是 TypeScript，两者在同一个工程里正常协作。
`tsconfig` 的 `include` 只覆盖 `.ts/.tsx`，所以 `npm run typecheck` 不会去检查 JSX 文件。

现有路由：

| 路径 | 页面 | 语言 | 登录态 |
|---|---|---|---|
| `/login` `/register` `/forgot-password` | 登录 / 注册 / 找回密码 | JavaScript | 无需登录 |
| `/personal-data` | 个人数据总览（6 个模块） | TypeScript | 需要登录 |
| `/study-guide` | 导学计划（登录后默认落地页） | JavaScript | 需要登录 |
| `/study-plan` | 学习计划编辑 | JavaScript | 需要登录 |
| `/study-timer` | 专注计时（番茄钟） | JavaScript | 需要登录 |

## 登录态与页面导航

四个业务页面共用一层整合逻辑，改动集中在三个文件，新加页面时了解一下即可，不需要每次都重新实现：

- `src/context/AuthContext.jsx`：应用挂载时调用一次 `GET /auth/me` 校验 session（HttpOnly cookie，浏览器自动带），暴露 `useAuth()` 给需要登录态的组件用。
- `src/components/RequireAuth/index.jsx`：路由守卫。未登录访问业务页面会被弹回 `/login`，并记下原本想访问的路径；登录成功后 `LoginPage.jsx` 会把用户带回原目标，没有原目标则去 `/study-guide`。
- `src/components/AppShell/index.jsx`：四个业务页面共用的顶部导航条（个人数据 / 导学计划 / 编辑计划 / 专注计时 + 当前用户邮箱 + 退出登录），只包这四条路由，登录/注册/找回密码页不受影响、保持各自原有设计。

**这次整合只做到「能登录、能互相跳转」，没有统一各页面内部的配色/字体/背景**——个人数据页用 `theme.ts` 这套令牌，其余三类页面（登录/番茄钟/导学计划）都各自定义了一套配色（主色分别是 `#7EC8E3`、`#4AD1FF`、`#009fff`），差异明显，是已知情况，不是这次要处理的范围。

### StudyGuide 与 StudyPlanEditor 的关系

两个页面内容目前高度相似（时间设置 + 任务设置 + 进入按钮），**不是重复实现**：设计意图是按历史数据量切换——数据不足时走引导式的 `StudyGuide`（对应 PRD 5.1「若无历史数据走规则模板」），数据积累到一定程度后走可编辑的 `StudyPlanEditor`（对应「若有历史数据，结合状态动态调整」）。

但 `mock-server` 目前没有 `/learning-records` / `/goals` 接口，做不了真实的数据量判断，所以现在**两个入口都摆在导航条里，不做自动切换**，等业务后端补上这两个接口后再把判断逻辑接上。「进入」按钮（`EnterButton.jsx`）两边都指向 `/study-timer`——按这份计划开始执行学习任务。

## 本地启动

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

需要认证接口时，另开一个终端：

```bash
cd mock-server
npm install
npm start              # http://localhost:4000
```

`frontend` 的 dev server 会把 `/api` 代理到 `:4000`，所以前端代码一律写相对路径 `/api/v1/...`，不要写死域名。

其他命令（都在 `frontend/` 下执行）：

```bash
npm run typecheck      # 仅类型检查（只查 .ts/.tsx）
npm run build          # tsc -b && vite build，产物在 frontend/dist/
npm run preview        # 预览生产构建
```

### 改代理目标

```bash
cd frontend
cp .env.example .env.local
```

在 `.env.local` 里改 `VITE_API_PROXY_TARGET`。留空时默认 `http://localhost:4000`。
业务后端（goals / learning-records / assessments）起来后改成它的地址即可，**不需要动任何 service 文件**。

注意 Vite 从 `frontend/` 读 env 文件，放仓库根目录不生效。

## 个人数据页

### 技术栈

| 项 | 选型 | 说明 |
|---|---|---|
| 组件库 | Ant Design 5 | 主题令牌在 `frontend/src/styles/theme.ts`，通过页面内的 `ConfigProvider` 注入 |
| 图表 | Recharts | 折线/面积/环形/仪表盘四类图共用一个库，比 @ant-design/charts 轻很多 |
| 样式 | CSS Modules | 零运行时；颜色走 `theme.ts`，字体走 `var(--font-title)` / `var(--font-body)` |

antd 的 `ConfigProvider` 和 dayjs 的中文 locale **收在页面组件内部**，没有放到全局 `main.jsx`——
同仓库里还有不使用 antd 的登录页，主题和 locale 不应该外溢过去。

### 目录

```
frontend/src/
├── pages/PersonalData/        # 页面入口，6 个模块纵向排列
├── components/PersonalData/   # 6 个模块组件 + SectionCard 卡片外壳
├── services/                  # 数据获取，每模块一个文件；http.ts 统一封装
├── hooks/usePanelData.ts      # 「先占位、再请求、失败保留占位」的统一逻辑
├── types/api.ts               # 严格对应 openapi.yaml 的 schema
├── types/view.ts              # 组件消费的视图模型（聚合结果）
├── utils/aggregate.ts         # 日/周/月聚合与格式化
└── styles/                    # theme.ts 设计令牌 + fonts.css 字体变量
```

`styles/global.css` 是**全局共享**的（由 `main.jsx` 引入），改动会影响所有页面，请谨慎。
个人数据页额外引入的 `fonts.css` 只定义 `--font-title` / `--size-*`，与 global.css 的 `--font-sans` / `--color-*` 不重名。

## 静态资源

`frontend/public/` 下的文件由 Vite 原样伺服在站点根路径，不参与打包也不加 hash，任何页面都能直接用绝对路径引用，
不需要 `import`：

| 文件 | 引用方式 | 说明 |
|---|---|---|
| `frontend/public/bg-sky.jpg` | `/bg-sky.jpg` | 天空背景图，1280×960 / 40 KB，色调与主题色板一致 |
| `frontend/public/brand/logo-mark-on-light.png` | `/brand/logo-mark-on-light.png` | 品牌图标（仅 EX 标记），黑色墨色，用在浅色背景上 |
| `frontend/public/brand/logo-mark-on-dark.png` | `/brand/logo-mark-on-dark.png` | 品牌图标（仅 EX 标记），白色墨色，用在深色背景上 |
| `frontend/public/brand/logo-full-on-light.png` | `/brand/logo-full-on-light.png` | 品牌全称版（EX 标记 + EpochX 文字），黑色墨色，用在浅色背景上 |
| `frontend/public/brand/logo-full-on-dark.png` | `/brand/logo-full-on-dark.png` | 品牌全称版（EX 标记 + EpochX 文字），白色墨色，用在深色背景上 |

品牌四图均为 1000×1000、真透明背景（PNG RGBA），可以直接叠加在任何底色上，不会出现白边。
命名规则是「用在什么背景上」而不是「墨色是什么颜色」——避免「白版」到底指白色文字还是白色背景的歧义。
选错一律会在浅色背景上看到几乎隐形的白字，或在深色背景上看到几乎隐形的黑字，遇到「logo 好像没显示」先检查是不是拿反了。

放 `public/` 而不是 `src/assets/` 是为了让所有页面都能直接引用——`src/assets/` 需要 `import` 且路径随目录层级变化。
文件名一律用 ASCII，中文名在 URL 里需要百分号编码，容易踩坑。

`mock-server/generate-email-logo.mjs` 会把 `logo-mark-on-light.png` 转成 base64 写入 `mock-server/email-logo.b64.js`（邮件模板内联用，避免邮件客户端拦截外链图片）。这个输出文件不是自动生成的，改了源图之后要重新跑一次：

```bash
cd mock-server
node generate-email-logo.mjs
```

## 接口对接现状

`openapi.yaml` 里**没有任何统计类接口**，所有日/周/月汇总均由前端基于 `GET /learning-records` 聚合完成，
聚合逻辑集中在 `frontend/src/utils/aggregate.ts`，后端若补统计接口可整体替换。

业务后端目前**尚未开发**，`mock-server` 只提供 `/api/v1/auth/*`。所以个人数据页现在全部跑在占位数据上，
每个卡片右上角会显示「占位数据」标记，悬停可看接口失败原因——不会白屏也不会静默假装成功。

| 模块 | 实际使用的接口 | 状态 |
|---|---|---|
| ① 打卡 | `GET /learning-records?dateFrom&dateTo` | 待后端 |
| ② 时长 | `GET /learning-records` + `GET /plans` | 待后端（目标时长借用 `Plan.availableMinutes`） |
| ③ 学科分配 | `GET /learning-records` 按 `subject` 分组 | 待后端 |
| ④ 专注度 | `GET /learning-records` 的 `selfReport.focus`<br>+ `GET /assessments/current` 的 `displayText` | 待后端（schema 即 1-5，无需换算） |
| ⑤ 日历 | `GET /learning-records` 按月拉取<br>+ `GET /assessments?subject=` 取每日状态标签 | 待后端 |
| ⑥ 目标 | `GET /goals?status=active` / `?status=archived` | 待后端（终态语义见下） |

### 关于状态标签：按学科展示，不做跨学科合并

模块④⑤都会显示状态标签（高效稳定 / 疲劳预警 / 情绪受阻 / 波动上升）。这些标签**一律取自服务端**
`GET /assessments`，前端不自行推算——PRD 6.1 规定「所有对用户可见的数字和结论性标签都来自规则层」。

该接口 `subject` 为必填、按单学科查询，PRD 5.2 也明确「不做跨学科的加权综合」，理由是避免
「语文情绪和数学正确率强行合并导致语义混乱」。所以 UI 上是**按学科分别列出标签**，
而不是合成一个「今天状态如何」的单一结论。这是产品的刻意设计，不是接口缺失。

### 需要后端补的字段

只剩 `Goal` 一个 schema 的 2 个可选字段，**纯增量、向后兼容**，不影响任何现有调用方：

```yaml
Goal:
  properties:
    outcome:                              # 新增，仅 archived 时有值
      type: string
      enum: [achieved, abandoned, expired]
      nullable: true
    completionNote:                       # 新增，目标完成总结
      type: string
      maxLength: 200
      nullable: true
```

**不要改 `status` 的 enum**——`active` / `archived` 被 `?status=` 过滤依赖，加平行字段才不会波及其他人。

前端已按「字段存在则用、不存在则退回当前行为」的方式读取（见 `frontend/src/services/goals.ts` 的 `toCard`），
所以**后端什么时候上线都行，前端不需要跟着改代码或重新发版**。在此之前 `archived` 统一显示为「已完成」，
完成总结显示为「待生成」。

另有一项低优先级、且有前端兜底方案的缺口：模块①的单日一句话总结。`/summaries` 的区间下限是 3 天，
生成不了单日。可行的替代是复用 `POST /learning-records` 自动创建的 `post_session` 建议
（`GET /recommendations?scene=post_session`，按 `generation.completedAt` 在前端归日），零契约改动。
当前该位置显示为「待生成」。

## 待办

- 构建产物单 chunk 超过 500 KB（主要是 antd）。黑客松阶段可忽略，需要优化时配 `build.rollupOptions.output.manualChunks`。
- `index.html` 没有声明 favicon（提交记录里写了「添加favicon」，但对应的 `favicon.png` 没有被提交，`mock-server/generate-email-logo.mjs` 也因此一度指向一个不存在的文件——已改成指向 `logo-mark-on-light.png` 让 `npm start` 能跑起来，但 favicon 本身还是缺的，需要重新加）。
- `StudyGuide` / `StudyPlanEditor` 的数据量驱动切换目前是摆设（两个入口都在导航条里，不会自动判断），等 `/learning-records` `/goals` 接口就绪后再接上，见上文说明。

## 设计系统(v0.3 · 2026-08-19 重构)

**视觉基调**:蓝天 + 白云 + 海浪,拟物/写实的液态玻璃(Liquid Glass)质感,参考 iOS 壁纸 + Linear 暗色 + Vercel 渐变。

**双主题模式**:
- 日间(默认):天空蓝渐变,白云,通透感强
- 夜间:深海蓝-靛蓝渐变,银白云,月光高光
- 切换入口:顶栏右侧 ☀️/🌙 按钮,全站 0.6s 平滑过渡
- 状态管理:`ThemeContext.jsx`,localStorage 持久化(key: `epochx-theme`)

**设计令牌**:
- 单一真源:`frontend/src/styles/tokens.css` v0.3
- 日夜间双套色板,通过 `[data-theme='day'|'night']` 属性切换
- 圆角收紧:卡片 8-12px,大卡片 16px,按钮 6-8px
- 液态玻璃工具类:`.liquid-glass`(多层高光:顶/左白色反光 + 底/右深色描边 + 内阴影曲面 + 外阴影)
- 字体:标题衬线(Noto Serif SC)+ 正文细体(Noto Sans SC 350)+ 数字等宽(JetBrains Mono)

**动效系统**:
- 开屏动画:`LaunchScreen` 组件,X 风格 Logo 放大 + 镂空透视 + 云层溶解,localStorage 记录已播放
- 页面过渡:`PageTransition` 组件,同级切换淡出+右滑入;`CloudTransition` 组件,主题切换全屏云层飘过
- 自定义光标:`CustomCursor` 组件,8px 圆点,hover 可点击元素放大到 20px
- 按钮 hover:上浮 2px + shimmer 扫光;卡片 hover:液态玻璃高光位移
- 骨架屏:`.skeleton-cloud` 云朵形状流动

**组件库**:
- 液态玻璃按钮:`.btn-liquid` / `.btn-liquid-primary` / `.btn-liquid-ghost`
- 液态玻璃输入框:`.input-liquid`(focus 时主题色边框 + 极淡光晕)
- 液态玻璃 Tab:`.tab-liquid`(选中态底部 2px 细线 + 文字加粗)
- 全部在 `global.css` 末尾,直接用 tokens.css 变量

**导航结构**:
- 6 项主导航横排:导学 / 计时 / 数据 / 复盘 / 建议 / 目标
- "我的"下拉:设置 / 资料建档 / 监护人授权
- 移动端:底部 6 Tab + "我的"抽屉

## 约定

- 新页面放 `frontend/src/pages/`，路由在 `App.jsx` 注册。不要新建第二个前端工程。
- 不要在组件里硬编码色值，一律从 `frontend/src/styles/tokens.css` 引用(`--lg-*` / `--glass-*` / `--primary*` / `--ink*`)。
- 不要在组件里直接 `fetch`，统一走 `frontend/src/services/`。
- 新增接口字段前先改 `docs/openapi.yaml` —— 它是前后端与 QA 的唯一契约来源。
- 改动**只限呈现层**,不要顺手改 service/hooks/数据语义(沿用上一任 agent 的铁律)。

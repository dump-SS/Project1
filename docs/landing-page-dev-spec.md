# 落地页开发实施文档（landing-page-dev-spec）

> **版本**：v0.1 · 2026-09-25
> **定位**：落地页从"设计定稿"到"可上线"的施工说明。**视觉与文案的唯一真源是 [visual-language.md](./visual-language.md)**，本文只写"怎么实现"，不重复设计结论；两者冲突时以视觉语言文档为准并回来改本文。
> **范围**：官网落地页（`域/`）。应用侧（`域/app`）与产品内视觉不在本文范围。
> **实测状态（2026-09-25 回填）**：第 3 节组件选型与 React 18 兼容已实测回填（§3.2/§3.3），性能数字见 §7；§5.3 卡 3 素材状态已按实际核实更正。落地页已在 `feat/landing-page` 分支实现完毕；八屏走查 + 四类降级实测（reduced-motion / reduced-transparency / 触屏 / 键盘）+ typecheck/build 全部通过（走查中发现并修复 4 处实现问题，见 §8 备注）。

---

## 1. 范围与前置

### 1.1 做什么 / 不做什么

| 做 | 不做 |
|---|---|
| 落地页路由与全部八屏 + 顶栏 + 页尾 | 产品内界面（`域/app`）、X1 壳与响应式 |
| 引入动效依赖（路由级分割） | 全站迁移 Tailwind（仅共存引入） |
| 图标绘制、实景图与实拍截图**占位** | 真实界面素材（等 M1） |

### 1.2 依赖与不依赖

- **不依赖重构**：叙事、文案、真对话素材（`docs/landing-conversation-samples.md`）已就位，可立即开工。
- **依赖 M1（X1 壳 + B 真链路）**：信任屏卡 1/卡 2 的实拍截图（见 §5.3）。**先放占位，M1 后替换，不要画两遍。**

### 1.3 共享文件铁律（必须遵守）

`frontend/src/App.jsx`、`vite.config.ts`、`package.json`、`styles/tokens.css`、`styles/global.css` 均由 X1/Skyer 收口。落地页要改的是：

| 文件 | 落地页需要什么 | 处理 |
|---|---|---|
| `App.jsx` | 注册 `/` 路由 | 提 PR 给收口人，**不自行改** |
| `vite.config.ts` | 新增 `build.rollupOptions.output.manualChunks`（当前未配置） | 同上 |
| `package.json` | Tailwind v4 + 动效依赖 | 同上 |
| `tokens.css / global.css` | **不新增全局规则** | 落地页样式全部写在页面级，避免污染全站（main.jsx 全局引入这两个文件） |

### 1.4 页面落点

- 目录：`frontend/src/pages/Landing/`（`AGENTS.md` 约定：新页面放 `pages/`，不新建第二个前端工程）。
- 落地页**不套 `AppShell` / `RequireAuth`**（那是产品内导航壳与登录守卫）。
- 组件内不直接 `fetch`；落地页目前无接口调用，若将来加（如桌面端订阅）走 `services/`。

---

## 2. 技术基线

现状（实测）：React 18.3.1 · Vite 5.4.11 · TS 5.6.3 · antd 5.21.6 · CSS Modules · alias `@ → src` · `/api` 代理到 8000 · `vite.config.ts` 已含 react 插件与 dev-login 中间件、**无 manualChunks**。

### 2.1 Tailwind v4：共存引入（本页是第一个落点）

**动因**：未来产品内引入 `beautifului.dev`（MIT）强依赖 Tailwind v4；落地页是全新代码、零迁移成本，适合当第一个落点。

**⚠️ 关键实现约束——只引入 utilities，不要 preflight**：

```css
/* 落地页样式入口（页面级，不进 global.css） */
@import "tailwindcss/utilities";
```

理由：仓库现有 **35 个 CSS / 9577 行** 与 49 个组件依赖既有基础样式，Tailwind 的 preflight 会重置默认样式、造成全站视觉回归。v4 支持只导入 utilities 层（不含 preflight 与主题重置），是共存的最安全路径。

- 安装：`@tailwindcss/vite` + `tailwindcss@4`（改 `package.json` 与 `vite.config.ts` → 走 §1.3 流程）
- 现有 CSS Modules 不动，**改哪个页面迁哪个**（渐进式）。

### 2.2 字体

⚠️ **仓库内没有任何字体文件**（`frontend/src` 与 `public` 下均无 woff/ttf），现有 `styles/fonts.css` 只定义变量（`--font-title` → serif、`--font-body` → sans，行高 1.75），实际依赖系统字体栈。

落地页需要的字体与待定项：

| 用途 | 字体 | 方案（待定） |
|---|---|---|
| 长段文本 / 小字（衬线） | 思源宋体 / Noto Serif SC | **子集化自托管**（全量中文字体过大）或 CDN；涉及加载策略与 FOUT 处理 |
| 标题 / UI / 数字（无衬线 + 等宽数字） | 现有 sans 栈 + JetBrains Mono 等宽 | 沿用现有变量 |

> 字体加载方案属**待定**（见 §9），实现前需拍板：自托管子集（体积可控、无外链）vs CDN（省事但有外链请求）。

### 2.3 代码分割

`vite.config.ts` 当前无 manualChunks，新增：

- 落地页路由整体 `React.lazy` → 独立 chunk。
- **重依赖（ogl / GSAP / three 系）只允许出现在落地页 chunk**，不得进主包。
- 首屏（hero）**不加载**任何重依赖 chunk：重动效按屏懒加载（进入视口前才取）。

---

## 3. 动效依赖引入

### 3.1 React Bits 接入路径（官方方式）

React Bits **没有独立 MCP server**，官方路径是 shadcn MCP + registry：

1. `components.json` 注册 registry：
```json
{ "registries": { "@react-bits": "https://reactbits.dev/r/{name}.json" } }
```
2. 配 shadcn MCP（`~/.workbuddy/mcp.json`）：
```json
{ "mcpServers": { "shadcn": { "command": "npx", "args": ["shadcn@latest", "mcp"] } } }
```
配完后需在连接器管理页点「信任」才生效。**本步尚未执行**，开工时再做。
3. 安装：`npx shadcn@latest add @react-bits/<Name>-TS-TW`。

**变体一律取 `-TS-TW`**（TS + Tailwind），与 beautifului 同一套。组件以**源码 copy 进仓库**（不装 react-bits 包），依赖 ogl / GSAP 等由组件自带。

### 3.2 候选组件（✅ 已实测回填，2026-09-25）

| 位置 | 组件 | 结论 | 体积（gzip） | reduced-motion | 触屏 | 备注 |
|---|---|---|---|---|---|---|
| Hero slogan | `TextType-TS-TW` | ✅ **采纳**（功能屏「写出」模式底座） | ~2 KB（去 gsap 后） | 无内置 → 调用方门控：reduced 时直显成稿 | 无关（纯文本） | 落盘改动见 §3.3；Hero 退格因需精确编排（删指定字+停顿）另写了时间线引擎 `useSloganSequence`，与 TextType 构成一删一写 |
| 页尾背景 | `Iridescence-TS-TW` | ✅ **采纳**（2026-09-25 Skyer 指定，**替换原 Grainient**） | 组件 3.27 KB（1.55 KB gzip）；ogl 复用 landing-gfx chunk，无新增依赖 | 无内置 → 落盘版加 `staticFrame`（静态单帧） | 指针推移图案（`mouseReact`），落盘版只在 hover 设备注册监听 | 亮色虹彩；离屏/切后台暂停为落盘版新增（上游无条件常驻 rAF） |
| 页尾背景（已弃用） | `Grainient-TS-TW` | ⛔ **被 Iridescence 取代**（文件保留未引用，不再进产物） | — | 落盘版有 `staticFrame` | 落盘版有 pointer 视差 | 若日后要回退，把 CtaFooter 的 lazy import 与 props 换回即可 |
| 页尾背景候选 | `Aurora-TS-TW` | ❌ 未采纳 | ogl ~12 KB | 无内置 | 无交互 | 极光带状形态偏「氛围灯」，流体感与页尾「鲜明」要求不符 |
| 页尾背景候选 | `Balatro-TS-TW` | ❌ 未采纳 | ogl ~12 KB | 无内置 | 有交互 | 像素化旋转质感是 Balatro 扑克游戏符号，与品牌无关 |
| 页尾背景候选 | `ColorBends-TS-TW` | ✅ **采纳**（2026-09-25 二次核反转）：实为**裸 three 全屏 shader**（无 r3f，React 18 兼容已验证），此前「r3f v9 仅 React 19」为误判；用于第二屏 logo 窗背景（Skyer 指定） | three ~150KB gzip | 无内置 → 调用方门控（reduced 不挂载） | 无交互依赖 | 挂载于进度 >0.5（logo 临近入窗），随 reveal 完整展出 |
| Hero 光场候选 | `Beams-TS-TW` | ✅ **采纳**（2026-09-25，用于**信任屏背景**而非 Hero 光场）：上游依赖 r3f v9（仅 React 19）→ 按「裸 three 落盘」先例**本仓移植**（shader/几何/灯光参数原样，零新增依赖） | three ~150KB gzip（共享 chunk） | 无内置 → 调用方门控（reduced 不挂载） | 纯背景无交互 | 品牌蓝光源（lightColor #4AD1FF）+ 深底 |
| Hero 光场候选 | `Ribbons-TS-TW` | ❌ 未采纳 | ogl ~12 KB | 无内置 | 无交互 | 流动丝带属装饰，过不了「它在讲什么」检验（§4 通用规则） |
| Hero 光场候选 | `Waves-TS-TW` | ❌ 未采纳 | 0（纯 Canvas 2D） | 无内置 | 有交互 | 波浪线簇形态偏「科技发布会」，与「光在你前方」的语义不符 |
| Hero 光场 | **CSS 径向渐变呼吸光场**（自实现） | ✅ **最终方案** | 0（零依赖） | `lp-breathe` 动画由 landing.css 统一静止 | 光晕无触屏依赖；指针视差仅 hover 设备 | 品牌蓝大面积低强度光晕 + 6–8s 呼吸 + 指针轻推 |
| 装饰类 | `PixelTrail` / `Ballpit` / `MagicRings` / `SplashCursor` | ❌ 不采用 | — | — | — | 均过不了「它在讲什么」检验，且 SplashCursor 与手电语言冲突 |
| CTA 输入框 | `GlareHover-TS-TW` | ✅ **采纳**（2026-09-25 Skyer 指定）：零依赖，hover 光泽扫过胶囊 | 0（组件 ~1.1 KB） | 无内置 → 仅 hover 触发，无动效即无影响 | 触屏无 hover → 不触发 | 尺寸走组件 `width/height` 属性（内联样式，类里写会被覆盖）；`cursor` 与聚焦态由调用方 module 覆盖 |
| 页尾页底 | `GradualBlur-TS-TW` | ✅ **采纳**（2026-09-25 Skyer 指定）：零依赖，纯 CSS mask + backdrop-filter 递进模糊 | 0（组件 ~3.6 KB） | 静态无动效 | 纯背景层 | `zIndex` 必须压到文字之下（合规声明不得被虚化）；落在 `.footer` 内，被卡片圆角与 `overflow:hidden` 裁住 |
| CTA 末句入场 | `FoldText-TS-TW` | ✅ **采纳（本仓移植，去 gsap）**：逐字片折入（`rotateX ±92°` + 透视 + 折痕明暗） | 0（组件 ~4 KB，零新增依赖） | 上游是动画 → 本仓落盘版加 reduced-motion 延迟归零 | 无关（纯文本） | 上游依赖 `gsap@^3`；`package.json` 是共享独占文件且仓库未装 gsap → 用 CSS 关键帧 + 逐片 `animation-delay` 复刻（细节见 §3.3）。⚠️ 字片必须 `padding-block: 8px`：衬线墨迹底边到 67.7px 而字片盒只有 62.4px，字片带 3D 变换/`will-change`（独立图层）会按自身盒子把墨迹裁掉——症状是「折入那句底部被切」（首句是普通块级，溢出不裁，所以只有后句出问题） |
| CTA 末句颜色 | `GradientText-TS-TW` | ⚠️ **未采用（改用同配方实现）** | 0 | — | — | 上游是「父元素 `background-clip:text`」；**实测该裁剪不作用于 3D 变换的子元素**（变换的字片完全不显形）→ 与 FoldText 无法嵌套。改为在 FoldText 落盘版里按字片实测偏移拼整行渐变（`background-size` = 行宽、`background-position` = −该片偏移），视觉配方与 GradientText 一致（实测量到逐片步进 0 / −36.25 / −67.77 / −102.24px，行宽 475.8px） |

> 实测环境：React 18.3.1 + Vite 5.4.11；体积来自 `npm run build` 产物（gzip）。

### 3.3 React 19 → 18 兼容验证（✅ 逐组件记录，2026-09-25）

| 组件 | 结论 | 详情 |
|---|---|---|
| `TextType-TS-TW` | ✅ 兼容（含改动） | 无 React 19 API（无 `use()` / ref-as-prop / Actions）；`ref` 经 `createElement` 传给 DOM 元素在 React 18 合法。**落盘改动**：光标闪烁 gsap 补间 → CSS 动画（`.lp-caret`），gsap 依赖整体移除 |
| `Iridescence-TS-TW` | ✅ 兼容（含工程化改动） | 纯 hooks + ogl，无 React 19 API。**落盘改动（shader 与算法原样）**：① 新增 `staticFrame`（reduced-motion 只渲一帧）；② 新增 IntersectionObserver + `visibilitychange` 暂停（上游无条件常驻 rAF，页尾在首屏外时会一直烧 GPU）；③ resize 改 ResizeObserver 观察容器，并把渲染分辨率上限压到 1920（片元 8 次循环，成本随像素数线性）；④ props → uniforms 原地同步、不重建上下文（上游把 color/speed/amplitude 放进 effect deps，改一个值就销毁重建并重置时间）；⑤ 指针监听只在 hover 设备注册；⑥ **速度用积分实现**（`uTime += dt × speed`，shader 里 `uSpeed` 恒 1）——直接改 `uSpeed` 会让相位 = 时间 × 速度在改值瞬间跳变，积分写法下可在底页「光变亮」时平滑提速 |
| `Grainient-TS-TW` | ⛔ 已弃用（被 Iridescence 取代） | 纯 hooks + ogl，无 React 19 API；落盘改动为指针交互 + `staticFrame`。文件保留在 `bits/` 但不再被引用（不进产物） |
| `FoldText-TS-TW` | ✅ 兼容（含去 gsap 改写） | 无 React 19 API。**落盘改动**：① gsap timeline → CSS 关键帧 + 逐片 `animation-delay`（i × stagger + 可选整体 `delay`），缓动换 `cubic-bezier(0.22,1,0.36,1)`；② 渐变字改逐片实测偏移拼整行（原因见 §3.2 表）；③ 样式改 CSS Module（上游注入全局 `<style>`）；④ `letter-spacing` 由 −0.04em 改继承（沿用页面 0.01em 口径）；⑤ reduced-motion 下 `animation-delay` 归零（landing.css 只压时长不压延迟）；⑥ **字片加 `padding-block: 8px` 防墨迹被自身图层裁掉**（见 §3.2 表该行备注） |
| `GlareHover-TS-TW` / `GradualBlur-TS-TW` | ✅ 兼容（原样落盘，无改动） | 均为纯 React + CSS，零依赖；GlareHover 不注册任何全局监听（只有 `onMouseEnter/Leave`） |
| three 系（Beams / ColorBends / Dither） | ❌ 不可用 | 依赖 `@react-three/fiber@^9` + `@react-three/drei@^10`，均要求 React 19；降级 r3f v8 需改组件源码，不值得引入 three（>600KB） |

> 已知教训（复验）：DotGrid 拖 GSAP 101KB gzip 的教训在本轮兑现——TextType 原版同样依赖 gsap，已通过 CSS 光标方案移除；全页最终 **0 个动画运行时库**（仅 ogl 44KB raw / 12.9KB gzip，且只随页尾懒加载 chunk）。

### 3.4 License

React Bits **MIT + Commons Clause**：产品内可用（含商用），**禁止打包成组件库转售**。我们不碰红线。beautifului 为 MIT。

---

## 4. 逐屏实现规格

通用规则（每屏适用）：

- 色板、字体、蓝色用法、文案红线一律查 `visual-language.md` §3–§6。
- **每屏蓝色只一处**（光晕或唯一焦点），见 §4 蓝色两种存在。
- 所有动效需能回答"它在讲什么"，答不上来就是装饰，删。
- 每屏都要有 `prefers-reduced-motion` 降级与移动端降级。

### 4.0 顶栏（全局）

| 项 | 规格 |
|---|---|
| 结构 | 左 logo（EX 标 → 滚过 hero 后全称 `EpochX` 从标识侧滑出并全程保持）；右 产品 / 定价 / 资源 + 登录 |
| logo 资源 | `public/brand/logo-mark-on-light.png`（深底用 `-on-dark`）。⚠️ 命名规则是"用在什么背景上"，拿反会隐形 |
| 定价 | 无展开面板；选项后**框住的小字「暂无」**（灰色描边标签，非蓝色） |
| 展开 | hover 任一项 → 整个顶栏下拉为 mega 面板 + 背景失焦虚化。产品：左「探索围绕你的下一代产品」+ 列表（EpochX Web / EpochX 桌面端）；资源：左「你需要的一切，在此获得最新动态和保持联系」+ 列表（文档 / 媒体 / 更新日志 / 隐私政策）。**菜单项 hover 文字滚动换字**（原字上滑出、同字由下方滑入，0.42s；副本 `aria-hidden` 不参与可访问名），**面板格子自上而下逐项淡入**（每档延迟 80ms，随面板重挂载重播）——Skyer 2026-09-25 口头指定，覆盖本文档原「面板整体淡入」描述 |
| 虚化 | `backdrop-filter` blur 8–16px **+ 半透明遮罩**；低性能与 `prefers-reduced-transparency` 降级为**纯遮罩** |
| 滚动行为 | 下滑收起、上滑弹出（上滑阈值 3px）。**⚠️ 锁定区间内禁用该行为**，区间内顶栏常显：① 第二屏跑道起点 → 梯形卡片收起点——**顶栏锁定延后到与第二屏梯形卡片同步收起**（Skyer 2026-09-25 口头指定），卡片开始左滑出屏幕的同一刻解除锁定；② **触底自动弹出**（Skyer 2026-09-25）：`scrollY + innerHeight ≥ scrollHeight − 4` 时强制常显，免得在页尾没有导航可用（离开底部后行为照旧）。多区间按 owner 注册（`lib/navScrollGuard.ts`）。
**信任屏的 `trustwall` 锁定已取消**（Skyer 2026-09-25：触底弹出只应发生在尾页，而该锁定会让顶栏一进隐私屏就冒出来，观感等同误触发）。信任屏劫持只是把纵向滚动映射成横向位移、**并未吃掉纵向滚轮**，顶栏收放不会抖动，故可照常工作（实测屏内 y 6098/7317/8536 均 `navTop −65` 已收起，仅触底 y 9475 时弹出）。代码以块注释保留在 `TrustWall.tsx`，需要时放开并重新 import 即可 |
| 页尾对比度 | 滚到页尾（亮色流体渐变）时**加深遮罩**，不切文字颜色 |
| 语言切换 | **登录左侧的「简体中文 ▽」**（Skyer 2026-09-25）：hover 展开小下拉，选项为另一种语言（当前项即按钮标签，故菜单只列非当前项）。`▽` 用 CSS 三角跟随 `currentColor`，展开时翻 180°；面板**宽度与触发按钮一致**（`width: 100%` + **显式 `box-sizing: border-box`**——本仓无 Tailwind preflight，默认 content-box 会把 12px 内边距 + 2px 描边加到宽度外、反而比按钮宽）、底色透明度也与按钮 hover 背景一致（同为 `rgba(27,34,45,0.7)`，原为不透明 `--lp-surface`），右对齐贴按钮下方并重叠 2px（显隐衔接不留 hover 空隙）。入场动画为**从上至下滑出**（`lp-lang-menu-in`：起点在终位上方 10px 落下，0.22s）——与左侧 mega 面板的 `lp-panel-fade`（从下往上）方向相反。**层级**：语言下拉必须压在 mega 面板之上（Skyer 2026-09-25 报 hover 左侧菜单后移到语言切换时下拉被遮）——面板与 `.bar` 同为 z-index 1 且面板在 DOM 中靠后，默认会压住整个 `.bar` 子树（连带语言下拉），故把 `.bar` 提到 **z-index 3**；顶栏内容与面板纵向不重叠，抬高 `.bar` 不改变面板观感。实测：按钮与面板同为 94px 宽、x 均为 1195、右缘同为 1289，面板背景 `rgba(27,34,45,0.7)` 与按钮 hover 背景逐字一致；面板展开（y 64–215）与下拉（y 50–100）重叠时，在下拉中心做 `elementFromPoint` 命中到下拉的 `ENG` 按钮（即下拉在上）、`.bar` z-index 3 > 面板 1。**下拉逻辑与左侧 mega 面板完全独立**（自持 `langOpen`/`lang` 状态，不碰 `openMenu`/`btnOffset`/面板渲染那套）。⚠️ **站内文案尚无 i18n**（全站仅中文）：切换只改按钮标签与选项，属占位——接 i18n 时从 `NAV_COPY.lang` 与这里的 `lang` 状态接出去。实测：hover → `aria-expanded=true` + 菜单出现 ENG；点选 → 标签变 ENG、菜单关闭；再 hover → 选项变「简体中文」；移出 → 收起；按钮 94px 宽、位于登录按钮（x=1301）左侧（x=1195+94≤1301）。窄屏（≤720px）隐藏该按钮：375px 实测 logo 标 + 三菜单 + 语言 + 登录排不下，且全站仅中文、移动端属可省项 |
| 可达性 | hover 之外支持 **click + focus 同效**、`Esc` 关闭（语言下拉一并收起）、焦点管理；移动端点击展开 |

验收：⌨️ 键盘可走完三个菜单；滚动到信任屏期间顶栏收放正常（不再强制常显，见滚动行为行）；页尾区文字对比度 ≥ 4.5:1；虚化降级生效。

### 4.1 Hero

- 布局：**上光下人**——上部 2/3 光场，底部"地平线"左 logo+slogan、右动作区。
- slogan 退格：初稿「学习工具围着题转！」→ 删「题」「！」→ 打「你」「。」→ 成稿「学习工具围着你转。」节奏见视觉文档 §7.1（打完停 1s → 退格先快后慢 → 删到「题」前半秒停顿 → 句号落下光标熄灭）。
- 暗纹 × 手电：学习物件 monoline 线稿（近不可见 `#2A3542`），鼠标扫过照亮显形。**手电机制只在本屏使用**，不推广到卡片/截图。
- **暗纹墙的「伪无限滚动」硬约束**（Skyer 2026-09-25 报「时不时刷新一下」→ 定位修复）：列内容 ×2 拼接后用 `translateY(±50%)` 循环，**前提是列元素高度 = 2 × 一个周期**。列作为行内 flex 项默认会被 `align-items: stretch` 拉伸到 `.colsWrap` 的高度（实测仅 881px），而内容高约 3058px → `-50%` 只有 −440px ≠ 周期 1529px → 每轮（80s）结束就整体跳一下。**修法**：`.wallCol { align-self: flex-start }`（按内容高，实测每列 half − period = 0）；时长同步 80s → 280s——位移从 440px 变 1529px，若仍取 80s 会快约 3.5 倍，调 280s 保持原观感速度（实测 ≈5px/s）。
- 动作区三级：输入框（主焦点）→ 即刻开始（主 CTA）→ 桌面端（虚线灰，空位）。
- **即刻开始配色（Skyer 2026-09-25 口头指定，覆盖原「品牌色填充」）**：`SpecularButton` tint `#2BA9E0` → `#EAF5FF`（极淡蓝近白，与 CTA 发送键同色、同 `--lp-pale` token），文字仍为深色 `#0B1017`。
- **即刻开始 hover（Skyer 2026-09-25「填充改近白后 hover 动效不明显，要更明显更鲜艳」）**：SpecularButton 的高光是「按指针接近度渐显的描边弧线」，在近白填充上等于隐形，故：
  - ① `.ctaBtn:hover` 把填充由极淡蓝转**品牌青 `#4AD1FF`**——`--sb-tint` 是组件**内联**写在按钮上的，必须 `!important` 才压得住（实测 computed `--sb-tint: #4ad1ff`、背景 `srgb(0.290 0.820 1)`）；
  - ② 同处加品牌青外发光 `0 10px 26px rgba(74,209,255,0.34)`（近白底上比描边更抓眼）；
  - ③ 描边参数同步调整以便在青底上可见：`lineColor #5CC8EC → #EAF7FF`（浅色）、`intensity 2 → 2.6`、`thickness 1.3 → 1.6`、`shineSize 10 → 14`；
  - 文字保持深色 `#0B1017`（青底上对比约 9:1）；`:focus-visible` 与 hover 同效（键盘可达）。
- 输入框 placeholder「先说一句，你今天怎么样？」；点击跳登录，**草稿带过登录墙**（登录后文本仍在）。
- 光场：呼吸 6–8s。

验收：slogan 退格时序正确、「你」为蓝字、手电只照亮暗纹不照亮 UI 文字、草稿跨登录不丢。

### 4.2 第二屏 · 三时代视窗

- 斜向平行四边形窄视窗，斜角 = logo X 的斜体角度。
- 滚轮驱动窗内横向流动：古代书简 → 书山题海 → 品牌 logo（统一暗蓝 duotone，logo 原色）。
- logo 入窗 → 视窗**右移 + 横向扩大**；历史段落主光收暗，logo 显现时光回归。
- 右侧文案：「AI 纪元，现围绕你构建。」+ 小字「一款围绕你的 AI 学习产品」，「你」= `#4AD1FF`。
- **滚动实现**：sticky section + scroll progress，**不全页劫持**；降级为三格静态图 + logo 定格。
- **顶栏锁定**：跑道起点 → 梯形卡片收起点（progress 0.68）向顶栏注册锁定区间，卡片开始收起时同步解锁（Skyer 2026-09-25）。

验收：三个时代停在一屏内；滚动到底自动释放；reduced-motion 下三图静态可见。

### 4.3–4.5 功能屏 ×3

- 标题 = 该屏对话里产品说过的**原句**，加「」+ 逐字打出 + 屏间切换动效（不新写文案）。
- 对话气泡裁剪为 **1 句用户 + 2 句产品**，**只删句子不改写**。
- 用户短句无衬线、产品长句衬线（字体时态规则）。
- 光晕落在对话上（本屏唯一蓝）；暗纹按屏换主题物件。
- ⚠️ 一页四次打字机会腻：hero 是**删词**、功能屏是**写出**，语义分工，实现时区分两者节奏（不要复制同一套参数）。

| 屏 | 标题 | 对话 | 暗纹主题 |
|---|---|---|---|
| 三 | 「坐了多久，和记住了多少，是两回事。」 | S2 | 秒表 / 成绩单 |
| 四 | 「错过的题，会变成路标。」 | S3 | 试卷 / 锥形瓶 |
| 五 | 「回头的时候，路都在。」 | S4 | 书 / 笔记本 |

验收：标题为对话原句且带引号、只删句未改字、每屏蓝色仅一处、打字机参数三屏不雷同。

### 4.6 信任屏

- 横向劫持滚动，四张卡片：标志 + 卡片 + 简要说明。
- 卡片：① 数据不出境 ② 不评判·不排名 ③ 监护人可撤回 ④ 不替你做决定。
- 交互：桌面 hover → 展开实拍图 + 详细介绍；**另加 click 同效 + Tab 可聚焦**；移动端配图不折叠 + 文字「展开」按钮。
- 横滚三护栏：**底部进度条 / 到底自动释放 / 支持触控板横滑与方向键**；标题「隐私安全当为先。」sticky 在左。
- 配图：卡 3 = 监护人授权邮件截图（mock-server 有模板，**真实存在**）、卡 4 = S5 对话（**真实存在**）；卡 1、卡 2 = **占位**，M1 后换真界面。

验收：键盘可展开每张卡；移动端不折叠；横滚能进能出；劫持期间顶栏收放正常（`trustwall` 锁定已取消）。

### 4.7 图标海屏

- 功能图标按"学生的一天"顺序：**计划 → 计时 → 记录 → 错题 → 知识点 → 复盘 → Chat → 收藏**，横向**无缝循环**（首尾接缝会露馅）+ 极慢滚动。
- 实现：React Bits `LogoLoop`（speed 80 / hoverSpeed 30），单元格 `li` 间距 `gap={28}`、单元格宽 142px（节距 170px）——**间距收紧**（Skyer 2026-09-25，原 gap 72 / 宽 168 → 节距 240）。
- **波浪浮动**：每个单元格 `translateY` ±16px、3.6s `alternate`，逐项 `animation-delay` 0.28s 错相（峰值逐格后移）。⚠️ **振幅与留白必须配套**：`LogoLoop` 根节点是 `overflow-x-hidden`，按 CSS 规范另一轴计算为 `overflow-y: auto` → 裁剪箱即单元格高度，下沉的图标会被裁掉；故根部 `paddingBlock: 26px` 撑大裁剪箱（26 > 16，全周期实测最小余量 10px）。
- 配文「功能有很多，中心只有你。」，「你」= `#4AD1FF`（小字衬线？— 配文为短句大字按无衬线处理，见字体规则）。
- **居中补偿**（Skyer 2026-09-25「看起来不居中」）：末字是全角句号「。」，字宽 1em 里右侧约 0.64em 是空白，而 `text-align: center` 按字宽盒子居中 → 可见文字偏左 0.32em（实测字宽 432px / 墨迹右沿 409px / 尾空 23px / 墨迹中心偏左 11.5px）。`.caption` 加 `transform: translateX(0.32em)` 补偿：位移后可见墨迹 508→917、中心 712.5 = 容器中心 712.5。按 em 给可随 `clamp()` 字号缩放，且不影响布局。
- 降级：静止排列。

验收：循环无接缝、滚动速度"盯着才看得出在动"、reduced-motion 静止、**浮动全周期图标与文字均不被裁切**（实测：32 个单元格 8s 采样，裁剪余量上 29.5px / 下 10px）。

### 4.8 CTA + 页尾

> 2026-09-25 Skyer 重排本节（口头指定，与本文档原描述出入处按口头为准）：紧凑上移、输入框胶囊化 + Glare Hover + 圆形发送键、两句改衬线、后句渐变 + 折入、页尾动效区左右留空 + 上两角大圆角 + 页底 Gradual Blur。

- **分区线**（Skyer 2026-09-25）：图标海与本节之间一条灰色发丝分割线——1px、`rgba(154,164,176,0.35)`（与顶栏面板竖分割线同色），**通栏**（不套内容栏，作为 `main` 直接子元素铺满视口宽，左右顶到屏幕边缘；实测 1425px = 视口宽），`aria-hidden` 静态无动效。
- **紧凑上移（后续调整）**：拉到底时 **① 末句落在视口顶下方约 71px**、**② 与上一屏的分割线必须已滚出视口**。算式：末句在底部的视口位置 = 视口高 − 180.4（末句→CTA 底：句盒 62.4 + 间距 32 + 胶囊 56 + 下留白 30）− 页尾高；故 `.footer { min-height: max(360px, calc(100dvh − 252px)) }`、`.cta { padding-block: 120px 30px }`（上留白 120 > 目标间距 71，分割线因此落在视口上沿之外）。实测末句 top = 71.4、输入框 165.8（未动）、卡片上边沿 251.8。
  - ⚠️ **末句与顶栏的净空只有 6.4px**：顶栏有「触底自动弹出」（见 §4.0 滚动行为），而末句距视口顶 71.4、顶栏高 64 → 顶栏弹出后两者贴得很近（截图观感像「顶栏下的页面标题」）。若要更多空气：`.ctaInner` 的 gap 调小（末句下移）或页尾 min-height 调大（整簇上移，但会压缩净空）——两者方向相反，需一起看。
- **末句与其下整簇的解耦**（Skyer 2026-09-25）：**末句位置只由 `.ctaInner` 的 gap 决定**（gap 变大 → 末句上移、其下不动），**而整簇在视口中的纵向位置由页尾 min-height 决定**（算式里的数变大 → 整簇上移）。改哪个要看清诉求：只抬末句改 gap，整体上移改 min-height。
- **矮窗兜底**：`@media (max-height: 700px)` 压缩页尾留白（`padding-block: 44px 30px`、`.legal` margin 30px）与末句间距（16px，与常规档同向收），min-height 改 `max(300px, calc(100dvh − 250px))`——否则视口高度 < 700px 时三段挤不下、末句会被顶出视口（实测 620px 高时末句 top = 81.6 仍完整可见）。
- **输入框**：与 Hero 同款胶囊（`border-radius: 999px`、高 56px、底 `rgba(27,34,45,0.72)`、描边 `rgba(140,160,180,0.16)`），外层套 `GlareHover`（hover 光泽扫过；实测 overlay `background-position` 由 `-100% -100%` 扫到 `100% 100%`）；宽度 560px（上限 100%）。**聚焦态**：描边转 `rgba(74,209,255,0.55)` + 三环外发光，**必须带 `transition: border-color/box-shadow 0.25s`**（Skyer 2026-09-25：原先点了是硬切、与 Hero 不一致）——GlareHover 根节点自身没有 transition 工具类，故在 `.inputGlare` 上补；`border-color` 需 `!important` 才压得过组件的内联 `borderColor`。实测 computed transition 与 Hero 输入框逐字一致（`border-color 0.25s, box-shadow 0.25s`）。**光泽参数**（Skyer 2026-09-25「太生硬且有点慢」后调柔调快）：`glareOpacity 0.22 → 0.12`、`glareSize 180 → 260`（光带更宽更柔）、`transitionDuration 700 → 420ms`；`glareColor #BFE9FF`、`glareAngle -45` 不变。
- **圆形发送键**：胶囊右内侧，44px 圆形、`var(--lp-pale)` = `#EAF5FF`（极淡蓝近白）、图标为黑色小纸飞机（`IconSend`，`color: #0B1017`）；点击进登录（与回车同效）。
- **末句两句英文改衬线**（`--lp-font-serif`）；首句「Nothing, without you.」淡出离场（0.35s，比入场略快以缩短交叉重叠）；**后句「You're everything.」= `FoldText` 逐字折入（18 字片，hinge top，逐片 35ms 延迟）+ 整行渐变字**（`#8FD3E8 → #4AD1FF → #3AA0E8`，去掉原候选里最深一档以保深底可读）。两句盒子严格同位（实测差 18.72px 即首句 −30% 离场位移；行高统一 1.2）。
- **页尾动效区**：左右留空 `margin-inline: clamp(20px, 3vw, 56px)`、`border-radius: 40px 40px 0 0`（上两角大圆角）、上边缘紧贴输入框（实测间距 31px）、页底 `GradualBlur`。
- **页底渐隐（GradualBlur）最终口径**（Skyer 2026-09-25 四次校准定型）：
  - **高度固定不变**：宿主 `position: fixed; bottom: 0; height: 30vh`（组件根 `preset="bottom"` + `height="100%"` 绝对铺满，掩膜百分比随宿主缩放）。30vh 的上沿（900 高视口下 y=630）正好落在页脚文字（logo/链接/版权/合规声明）下方 → 静止时文字全清晰，只有卡片下半的空白渐变成软边。
  - **渲染时机 = 「分割线与末句的中点」滚进视口**（Skyer 2026-09-25：不要卡在分割线处触发，往下挪到两者之间）：`mid = (分割线.top + 末句.top) / 2`，`mid < window.innerHeight` 即点亮（0.4s 淡入），滚回去自动熄灭。取中点而非写死偏移量，上方留白改了也不会失准（实测触发瞬间 分割线 y≈700、末句 y≈820、mid≈760；早于此 mid≥1108 时为熄灭）。
  - 实测：`mid 1457 → op 0`；`mid 760 → 0.93`（淡入中）；`mid 551/342/133 → 1`；带高恒为 270px、带上沿恒为 630。带内内容（logo/链接/返回顶部）明显发虚，带外（末句/输入框）清晰——对照关闭 `backdrop-filter` 的一帧全清晰。
  - 更早的两版（绝对定位贴页面底、上沿随分割线伸缩）都已被这版取代：前者滚入时不在屏幕里故不可见，后者与「高度固定」的要求不符。
  - 🐞 **「始终看不到」的真因（2026-09-25 定位，与强度/位置/mask 均无关）**：`GradualBlur` 的渐变层用 Tailwind **`absolute inset-0`** 定尺，而本页只引 `tailwindcss/utilities`、**没引 theme**（见文件头注释）→ `inset-0` 编译为 `calc(var(--spacing) * 0)`，`--spacing` 未定义 → 整条声明被丢弃 → 三层实测都是 **0×0**，`backdrop-filter` 无从作用。对照实验：手写的 `backdrop-filter: blur(24px)` 层（带/不带 mask）都正常糊 ✓，只有组件层是 0×0 ✗。**修法**：`landing.css` 加 `.landing .gradual-blur > div > div { inset: 0 }`。
  - ⚠️ 同类风险：`TiltedCard`（`top-0 left-0`）、`GlassSurface`（`p-2`）也用了主题相关工具类而静默失效——当前视觉无碍，但新增组件务必**只用任意值语法**（`text-[#4AD1FF]` 这类）。
  - ⚠️ **性能**：固定全宽 backdrop-filter 的层数/半径决定合成成本，实测 7 层/末层 96px 时预览连截图都准备不出来（滚动必然掉帧）。现为 3 层 / 上限约 30px（`strength 1.9 / divCount 3 / exponential`，层值 `blur(3.9)/blur(14.9)/blur(30.4px)`）；`prefers-reduced-motion` 下整条不渲染。
  - 宿主 `z-index: 100` 压在页尾内容之上、顶栏面板之下。
- 页尾背景 = **`Iridescence`**（2026-09-25 Skyer 指定，替换原 Grainient）：亮色虹彩、有流动感、指针推移图案。落盘参数：基色 `[0.86, 0.95, 1]`（带蓝品牌倾向的亮色；全白会偏「彩虹纸」）、`amplitude 0.12`、`speed` 底页提速 `0.32 → 0.85`（与末句翻转同一拍，即原「光变亮」）；`staticFrame={reduced}` 走静态帧。配套：`.bgScrim` 由 `0.55/0.68` 降到 **`0.26/0.36`**（Iridescence 输出本身偏亮，scrim 只为兜文字对比度，压太浓会把虹彩糊没）；`.bgFallback` 改成虹彩的静态近似（淡青 + 淡紫 + 淡薄荷三层径向）。构成：logo + 一句话简介（暂填「围着你转的学习伙伴。」）+ 链接组 + 返回顶部 + 版权行。
- **返回顶部 = GlassSurface 胶囊**（Skyer 2026-09-25，原为半透明浅色方块圆角 8）：玻璃层是绝对定位兄弟节点（`.backTopGlass`，`border-radius: 999px` + `overflow: hidden` 让玻璃按胶囊裁切），文字/图标各自 `position: relative; z-index: 1`——裸文本节点无法定层、会被玻璃盖住；按钮自身透明，底色由玻璃层给（`.glassPill { background: rgba(255,255,255,0.34) !important }`，因 GlassSurface 按 `prefers-color-scheme` 选底色而本页恒为亮区页脚）；hover 提到 0.5 + 上浮 1px；`prefers-reduced-transparency` → `.backTopSolid` 纯色底（与顶栏同一降级口径）。实测按钮 115×40 / radius 999、玻璃层 `backdrop-filter: url(#glass-filter…) saturate(1.3)`、hover 背景 0.34 → 0.5。
- 链接组 = **四个「品类母项」单行并置**（Skyer 2026-09-25：原 2×2 网格改成横行并置；母项**不可点击**，具体子项未定）：渲染成 `<span>` 而非 `<a>`，保留虚线占位样式以示「结构留位、内容留空」；`.links { display: flex; flex-wrap: wrap; gap: 10px 28px }`（窄屏自动折行）。**下划线与间距**（Skyer 2026-09-25 二次调整：「拉开间距、下划线长度统一、左端与文字对齐、右端长于文字」）：不用 `border-bottom`（长度随文字长短变化），改固定等宽盒 `width: 96px` + 绝对定位 `::after` 画满整盒——文字左对齐，下划线左端自然贴文字、右侧余量就是「长于文字」；`.links` 的 `gap` 由 `10px 28px` 放大到 `12px 42px`。实测四项均 96px 宽、下划线 `width: 96px / left: 0` 全一致，文字宽 57/57/72/57px（即右端分别出格 39/39/24/39px），整组仍单行（组宽 327 → 510px），`clickable: false`。调下划线长度只需改那个 96px。子项定下来后挂下一级入口，母项本身仍不做可点入口。
- ⚠️ **合规硬项**：页尾显著标注「**学生团队开发，pilot 封测，不代表最终产品形态和品质**」（Skyer 2026-09-25 改文案，原为「学生团队开发，未经专业法律审核」）。GradualBlur 的 `zIndex` 因此必须压在文字之下（只渐隐背景）。
  - ⚠️ **与 PRD 的措辞差异（待团队确认，非我能单方改）**：PRD §6.2 与 §778 仍以「学生团队开发，未经专业法律审核」作为 pilot 口径下替代法务评审的标注要求；现文案去掉了「未经专业法律审核」、改为「pilot 封测，不代表最终产品形态和品质」。两条都是向用户披露，但披露内容不同，若 PRD 那行仍属硬要求，需要同步改 PRD 或把两句合并。
- ⚠️ **占位规则**：联系方式、协议链接地址、社区与文档入口、备案信息——**结构留位、内容留空，不预先编造**。
- ✅ **版权行已落地**（2026-09-25 Skyer 给定）：`© 未名_Official 2026`——`FOOTER_COPY` 增 `copyrightHolder: '未名_Official'` 与 `copyrightYear: '2026'`，原先的虚线下划线占位（`.blank`）随之删除；备案信息行仍按占位规则留空。

验收：底部两区不互相遮挡；句子翻转与光效同步；合规声明可见且清晰；占位项无编造内容。

---

## 5. 素材清单

### 5.1 图标（约 20 个，需绘制）

**统一规格**：monoline 线稿 · stroke 1.5 · 24×24 网格（`viewBox="0 0 24 24"`）· `currentColor` · 无填充 · 圆角端点 · SVG 组件或 sprite。

**暗纹物件（hero 背景 + 功能屏主题）**：成绩单、书、笔记本、铅笔、尺子、圆规、三角板、锥形瓶、烧杯、试管、地球仪、显微镜、秒表。
**功能图标（图标海屏）**：计划、计时、记录、错题、知识点、复盘、Chat、收藏。
**UI 小图标**：返回顶部箭头、展开箭头、外部链接。

### 5.2 实景图（2 张，占位）

| # | 内容 | 要求 |
|---|---|---|
| 1 | 古代书简 | 横构图（窄视窗内横向流动，建议 3:2）· 统一**暗蓝 duotone** · 无水印 · 商用授权明确 |
| 2 | 书山题海（应试教育） | 同上。**建议自拍**——学生真试卷/错题本堆比图库摆拍更贴定位，成本是一节课间 |

### 5.3 实拍截图（占位，M1 后替换）

> ⚠️ **2026-09-25 核实更正**：原表把卡 3 标为「真实存在（mock-server 模板）」——实际核查 mock-server 只有注册/登录/重置验证码邮件模板，后端 guardian 流程 MVP 阶段不真发邮件（`backend/routes/user.py`），**监护人授权邮件模板并不存在**。经拍板（D4）：卡 3 与卡 1/2 一致做占位块 + TODO，M1 后统一替换真素材。

| # | 位置 | 内容 | 状态 |
|---|---|---|---|
| 1 | 信任屏卡 1 | 数据不出境相关界面 | ⏳ 占位（M1 后） |
| 2 | 信任屏卡 2 | 不评判·不排名相关界面 | ⏳ 占位（M1 后） |
| 3 | 信任屏卡 3 | 监护人授权邮件截图 | ⏳ 占位（原标「真实存在」有误，见上方更正；M1 后） |
| 4 | 信任屏卡 4 | S5 对话 | ✅ 真实存在（跑批产出，v1.1） |

占位实现：等比容器 + 中性占位块 + 明确 TODO 注释，**不得用假界面图顶替**。

### 5.4 字体

见 §2.2，方案待定（子集自托管 vs CDN）。

---

## 6. 无障碍与降级矩阵

| 场景 | 降级要求 |
|---|---|
| `prefers-reduced-motion` | 所有滚动驱动动画静止；退格动效直接显示成稿；打字机直接显示；流体渐变静态；图标海静止 |
| `prefers-reduced-transparency` | 顶栏虚化 → 纯遮罩 |
| 移动端 / 触屏 | 无 hover：顶栏菜单改点击、信任屏配图不折叠 + 展开按钮、手电取消（暗纹低辨识度常亮）；重背景简化或静态 |
| 键盘 | 顶栏菜单可 focus 展开、Esc 关闭；信任屏卡片可聚焦展开；所有 CTA 可达 |
| 低性能设备 | 重动效 chunk 延迟加载或跳过；提供静态兜底 |

---

## 7. 性能预算（✅ 2026-09-25 实测回填）

> 数据来源：`npm run build` 产物（`dist/assets/`）gzip 实测 + 浏览器 `performance.getEntriesByType('resource')`。

| 项 | 实测 | 说明 |
|---|---|---|
| **主包** | 664 KB gzip（`index-*.js`） | antd 为主的既有体量；**落地页未向主包新增任何依赖**（gsap 已剔除，ogl 只进 gfx chunk） |
| **落地页路由 chunk** | 11.9 KB gzip（32.2 KB raw） | `React.lazy` 独立分包，首屏产品页不加载 |
| **landing-gfx chunk（ogl）** | **12.8 KB gzip**（44.4 KB raw） | 仅页尾 Grainient 接近视口（`40% 0px` rootMargin）才动态 import；`manualChunks` 强制 gsap/ogl 与主包分离 |
| **Grainient 组件 chunk** | 3.0 KB gzip | 随 gfx chunk 一起懒加载 |
| **动画运行时库** | **0 个** | gsap 已从 TextType 移除（改 CSS 光标）；Hero 光场为纯 CSS 径向渐变呼吸（零依赖） |
| **字体（子集自托管）** | NotoSerifSC-lp.woff2 85 KB + NotoSansSC-lp 400/500 各 66 KB，`font-display: swap` | 落地页元素全部走 `LP-Serif`/`LP-Sans` 本地字体，**零外部字体请求**（实测 network 仅 1 个外部请求 = `index.html` 既有的 Google Fonts CDN link，产品内页面全局依赖，非落地页发起；其按需化留待产品内页面后续处理） |
| **LCP < 2.5s（4G 模拟）** | ⏳ 待真机校准 | 构建产物已满足结构前提（首屏 JS = 主包 + 路由 chunk，重依赖与字体均不阻塞渲染；字体 swap 不挡首绘）。真机 LCP 数值需 DevTools 4G 节流实测后补录 |

---

## 8. 验收清单（✅ 2026-09-25 走查完成，浏览器实测 1440×900 + 375×720）

- [x] 顶栏：logo 两态、三菜单、定价「暂无」灰标签、虚化与降级、滚动收起/弹出、信任屏区间不抖、页尾加深遮罩
- [x] 顶栏交互收尾（2026-09-25 实测回填）：菜单 hover 文字上滑出/下方滑入；面板格子自上而下逐项淡入（rAF 采样：42ms 全 0 → 202ms 0.88/0.46 → 401ms 1/0.99/0.94/0.71 → 702ms 全 1）；第二屏锁定区间内下滑常显、越过卡片收起点后恢复收起（实测 y=1929 常显 / y=2049 收起，卡片收起点 y≈1958）
  （实测：EX 标→全称滑出、mega 面板 click/hover 展开 + Esc 关闭、下滑收起/上滑弹出断言、劫持区间常显、`navFooter` 加深生效）
- [x] Hero：退格时序、手电只照亮暗纹、三级动作、草稿跨登录
  （实测：初稿「学习工具围着题转！|」打字态与成稿「围着你转。」截图、localStorage `epochx.landing.draft` 写入 + 刷新恢复、桌面端 disabled 虚线）
- [x] 第二屏：三时代一屏内、视窗扩大动效、光收暗与回归
  （实测：斜切视窗、logo 段定格、sticky 跑道到底自动释放进入图标海）
- [x] 功能屏 ×3：标题为对话原句、只删句未改字、每屏一处蓝、打字机参数不雷同
  （实测：三句标题均带「」逐字打出，峰值态清晰；滚动切换低谷态为正常屏间过渡）
- [x] 信任屏：四卡、hover/click/focus 三种触发、横滚三护栏、配图来源正确（1 真 3 占位）
  （实测：click/focus 展开断言、底部进度条随推进、sticky 跑道到底自动释放、卡 4 = S5 真对话完整呈现。⚠️ 卡 3 按 §5.3 更正为占位，原「2 真 2 占位」口径随之修正）
- [x] 图标海：无缝循环、极慢、顺序为"学生的一天"
  （实测：8 图标 ×2 复制双份结构，顺序 计划→计时→记录→错题→知识点→复盘→Chat→收藏）
- [x] CTA+页尾：句子翻转与光同步、两区不遮挡、合规声明可见、占位无编造
  （实测：滑到底「You're everything.」蓝色翻转 = 光全开同一拍、暗区/亮区边界清晰、合规声明显著、链接/年份/备案全部结构留位）
- [x] 全局：reduced-motion / reduced-transparency / 触屏 / 键盘 四类降级实测
  （实测：① reduced-motion——dist 注入 matchMedia 垫片强制：Hero 成稿直显、信任屏静态网格全展开、页尾 canvas=0 走静态 fallback、CTA 翻转正常；② reduced-transparency——dist CSS 强制生效：`backdrop-filter: none` + 纯遮罩 `rgba(16,22,30,0.92)`；③ 触屏（hover:none 垫片）——手电/Grainient 指针注册的 JS 门控关闭、展开按钮在无 hover 设备显示（CSS 反转验证）；④ 键盘——Tab 聚焦信任卡即展开、Esc 关闭菜单）
- [x] 全局：重依赖只在落地页 chunk；主包无新增重依赖（见 §7 实测表）
- [x] 素材：图标约 20 个齐备、2 张实景图到位、截图占位标注 TODO
  （实测：24 枚 monoline 图标、实景图 2 张 duotone 占位 + 3 张截图占位（卡 3 更正后）均带 TODO，无假界面图）

**走查中发现并已修复的实现问题**（均为代码缺陷修复，不涉及视觉/文案拍板项）：

1. **CTA 翻转句与输入框重叠**：`.finalLine` 固定 1.2em 高，翻转句 `.lineIn` 处于文档流成为第二行溢出压住输入框 → 改为与首句同位叠放（`position: absolute; inset: 0`）交叉淡入。
2. **信任屏标题叠压卡片**：卡片横移滑过标题区，55% 半透明卡面透出标题文字 → 标题随横移进度在前 25% 内淡出（「sticky 在左」初始语义不变，淡出让位给卡片；供 Skyer review，如需标题全程可见可改卡片轨道裁切方案）。
3. **信任卡折叠态内容泄漏**：`.figure` 的 `0fr` 折叠被子元素自身 margin/padding/边框撑起轨道下限（实测漏出 38px 的 S5 对话切片与占位框虚线顶边）→ 增加零装饰裁剪层 `.figureClip` 作为 grid 直接子元素。
4. **移动端顶栏菜单折行破碎**（375px 实测）：菜单/登录按钮文字竖排换行 → `white-space: nowrap` + 720px 断点紧凑化（字号/间距收紧）。
5. **纵向 flex 里 `width: auto` 的图片会被横向拉伸**（踩了两次：Hero logo 与页尾 logo，均实测渲染宽度 ≈ 容器宽）——纵向 flex 容器默认 `align-items: stretch`，交叉轴（宽）被拉满，而 `width: auto` 不构成防御 → 图一律加 `align-self: flex-start`（Hero `.logo`、页尾 `.footerLogo` 已加并留注释）。全页排查脚本：比对每个 `<img>` 的 `rendered 宽高比 / naturalWidth/naturalHeight`，偏离 >2% 即拉伸；当前仅第二屏两张实录图命中，那是 `.slideImg { object-fit: cover }` 的有意裁切，不算拉伸。
6. **揭示类逻辑不能只押 IntersectionObserver**（2026-09-25「Iridescence 没了」）：页尾虹彩背景原用 `useInView('40% 0px')` 门控渲染，实测该 IO 会**漏回调**，一旦漏掉就渲染 `.bgFallback`（同为淡青淡紫渐变）——观感就是「虹彩变淡/没了」；同一次排查还发现三节叙事屏 `.section` 的未入场态是 `opacity: 0`，漏回调即整屏空白。更极端的是预览环境合成器冻结时 **`requestAnimationFrame` 整段不派发**（实测 rAF 复查一次都没执行）。处置：① 虹彩背景去掉门控、直接挂载，组件内部暂停的 `isVisible` **初始取 true**（漏回调最坏只是多渲几帧，不会空白）；② `useInView` 改成三重保险——IO + scroll/resize 的 rAF 节流复查 + **1s `setInterval` 里同步 `getBoundingClientRect`**（最后一道不依赖任何异步回调，rAF 冻结也生效），命中后整体摘除。实测：叙事屏三节随滚动依次入场、正文不再空白。

---

## 9. 英文版（i18n）· 2026-09-27

Skyer 决策：**只做落地页**（应用内页面不动）、**全量翻译**（含三屏真对话样本、隐私四卡长文、合规声明）、**英文由我直译并标「待 review」**。

### 9.1 机制

| 项 | 做法 |
|---|---|
| 依赖 | **零新增依赖**：`frontend/package.json` 是共享独占文件（AGENTS.md 铁律 3），落地页文案本就集中，故用 `content/i18n.tsx` 的 Context + 字典 |
| 文案结构 | `content/copy.ts` 只放 **interface + re-export**；`copy.zh.ts` / `copy.en.ts` 两套同形文案。用显式 interface 而非 `typeof COPY_ZH`，保证**漏翻一条即编译不过** |
| 语言来源 | ① URL `?lang=en\|zh`（可分享，优先）→ ② `localStorage['epochx.landing.locale']` → ③ 默认 zh |
| 切换副作用 | 写 localStorage + `history.replaceState` 同步地址栏（不留历史记录）+ 设 `<html lang>`（读屏/字体回退/浏览器翻译提示都看它）；首次挂载把解析结果落盘，故走 `?lang=en` 链接进来的人下次访问根地址仍是英文 |
| 组件消费 | `useCopy()` / `useLocale()` / `useDialogues()`；`LandingLocaleProvider` 挂在 `Landing/index.tsx` |
| 真对话 | `content/dialogues.ts` 改为 `DIALOGUES_BY_LOCALE`（zh/en 同形），英文逐句对应、不增删句子 |

### 9.2 双语化时必须清掉的「语言硬编码」（都已改）

| 位置 | 原写法 | 现写法 |
|---|---|---|
| Hero 加粗段 | `StrongProximity` 写死 label「围着」「你」「转」 | 按当前语言 `strong` + `highlight` 拆三段（high 段为空则不起 VariableProximity） |
| Hero 蓝字 | `renderWithYou` 用 `indexOf('你')` | `indexOf(highlight)` + 按 `highlight.length` 整段染色（英文 you 是三个字符） |
| 第二屏标题断行 | 按中文逗号 `indexOf('，')` 拆两行 | 文案显式给 `headlineLines`，不再靠标点 |
| 第二屏蓝字 | `s[idx]` 单字染色 | 按 `highlight` 整段匹配染色 |
| 隐私卡占位 | 组件内硬编码「界面截图 · 待接入」 | `trust.placeholderLabel` |
| 读屏标签 | 组件内硬编码「三时代」「隐私安全」「功能一览」「开始使用」「主导航」「页脚链接」「发送」「真实对话」「EpochX 首页」等 | 统一收进 `a11y.*`（英文版读屏必须念英文） |

### 9.3 英文专属调整（待 review）

- **Hero slogan 字号**：英文句（"Learning tools, built around you."）≈ 中文 11 字的 2 倍宽，沿用中文档 `clamp(30px,4.6vw,56px)` 会在中等宽度折行 → 英文档 `.sloganEn { font-size: clamp(26px,3.5vw,44px) }`（实测 1440×900 下成稿 695px 一行）。
- **Hero slogan 换词结构**：中文「学习工具，围着**题**转」→「学习工具，围着**你**转」；英文同构 **Learning tools, built around _questions_** → **…_**you**_（`base` = 公共前缀，退格退到 base 再打 strong）。
- **真对话的翻译披露**：中文角标声明「对话为测试期间产品真实生成」；英文沿用同一句而不说明翻译＝夸大素材来源，故英文角标补 **(translated)**。
- **不译项**：品牌名 EpochX / EpochX Web、版权持有者「未名_Official」（账号名，保留原写法，故英文页仍有一处中文，属有意）。
- **CTA 末句**（Nothing, without you. / You're everything.）两种语言一致——本就是英文原句。

### 9.4 待 review 清单（review 时按这个顺序看）

1. `content/copy.en.ts` 全文（约 80 条）——尤其三屏 `featureScreens.description`（技术说明段，信息密度最高）；
2. `content/dialogues.en.ts` 的三段真对话 + S5 整段（语气、称呼、"你"的译法是否统一用 you）；
3. §9.3 的四条英文专属调整；
4. 英文 slogan 的语义（"built around questions" 对应「围着题转」是否达意）。

---

## 10. 待定与待实测

**待实测（✅ 2026-09-25 全部回填完毕）**

1. ~~动效组件选型（§3.2 候选表）~~ → 已回填（采纳 TextType / Grainient + 自实现 CSS 呼吸光场；three 系组件因 React 18 不兼容整体否决）
2. ~~React 19→18 逐组件兼容验证（§3.3）~~ → 已回填
3. ~~性能预算具体数字（§7）~~ → 已回填（LCP 真机校准一项待补）

**待拍板**

1. ~~字体加载方案：子集自托管 vs CDN（§2.2）~~ → **已定：子集自托管**（已落地 `public/fonts/` 3 个 woff2）
2. 落地页开发顺序与 X1 壳的协调（§1.3 共享文件）——共享文件改动已按用户授权直接提交（单独 commit 标注待 review）
3. ~~是否分两阶段（先静态版再叠动效）~~ → **已定：不分阶段，动效一次加齐**（Skyer 拍板）。代码分割与懒加载策略仍然照做（§2.3），那是加载策略不是交付阶段。

**遗留待确认（实现期间记录，不阻塞上线走查）**

1. 功能屏三句标题在 S3/S4 跑批对话中无逐字出处（按 visual-language 定稿执行，`content/copy.ts` 头注有标）。
2. 信任屏四卡「简要说明」正文为按要点的最小扩写稿，待 Skyer review。
3. 顶栏「资源」四项与页尾链接组的指向（占位规则：结构留位、内容留空）。
4. 桌面端按钮 disabled 的最终交互（订阅通知属占位内容，默认不做）。
5. reduced-motion 下打字机光标仍存在于 DOM（视觉已隐藏，仅语义洁癖层面可优化）。

---

*本文依赖 [visual-language.md](./visual-language.md)（视觉与文案真源）与 [landing-conversation-samples.md](./landing-conversation-samples.md)（真对话素材）。改动视觉/文案请先改那两份，再回来同步本文。*

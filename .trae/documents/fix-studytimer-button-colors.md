# 计时页"开始"键 + 学习小结"完成"键 配色修正

## Why

`StudyTimer` 页面顶部计时控件里的"开始"按钮（`.btn.primary`）文字颜色当前为 `var(--blue-1)`，而 `--blue-1` 在 `index.module.css` 第 8 行被桥接到 `var(--glass-fill)`：

- 日间模式 → `rgba(255, 255, 255, 0.42)`（半透白）→ 在主色蓝底上对比度偏弱
- 夜间模式 → `rgba(16, 24, 44, 0.42)`（半透深夜蓝）→ 文字几乎与亮蓝背景同色，肉眼难辨

"开始"是计时页最高频操作键，需要在两种主题下都**清晰可读**。最直接的修法是去掉这个跟随主题的桥接，把文字固定为不透明纯白。

`StudyTimer` 弹出的"学习小结"对话框（`RecommendationPanel`）里的"完成"按钮（`.popOk`）当前是深蓝渐变背景 + 白色文字，视觉权重与"再学一轮"（`.popRestart`）的反差不够，且与 PRD「学习小结」作为"收束"动作的语义也不太匹配——通常"完成"是收束键，应以更轻的视觉呈现。改为浅蓝文字能让"完成"在视觉上从主操作降为次操作（与"再学一轮"形成 ghost-vs-ghost 对称）。

用户已明确"所有在夜间和白天均可以明显体现"，所以要选在两种主题下都对比充足的浅蓝色 + 配套背景处理。

## What Changes

- 修改 `frontend/src/pages/StudyTimer/index.module.css` 中两个 class 的颜色/背景：
  1. `.btn.primary` 的 `color` 由 `var(--blue-1)` 改为 `#ffffff`（固定不透明纯白）
  2. `.popOk` 改为 ghost 风格：背景透明 / 边框 1px 浅蓝 / 文字浅蓝，**不**保留当前的深蓝渐变背景——否则浅蓝文字落在浅蓝渐变上两种主题都会糊

## Impact

- 受影响页面：
  - `/study-timer` 顶部"开始 / 继续 / 重新开始"按钮（同一个 `.btn.primary`）
  - `/study-timer` 计时结束后的"学习小结"弹窗中的"完成"按钮（`.popOk`）
- 不影响其他组件的按钮样式（不同 class 各自独立）
- 不需要改 React 组件 / 不需要新依赖 / 不需要改后端

## ADDED Requirements

### Requirement: `.btn.primary` 文字固定为白色
#### Scenario: 日间模式
- **WHEN** 页面处于日间主题（`--blue-1` = 半透白），用户看到"开始"按钮
- **THEN** 按钮文字为不透明 `#ffffff`，对比度充足

#### Scenario: 夜间模式
- **WHEN** 页面处于夜间主题（`--blue-1` = 半透深蓝），用户看到"开始"按钮
- **THEN** 按钮文字仍为 `#ffffff`（不跟随主题变化），在亮蓝渐变背景上可读

### Requirement: `.popOk` 改为浅蓝 ghost 风格
#### Scenario: 日间 / 夜间模式通用
- **WHEN** 学习小结弹窗出现，"完成"按钮渲染
- **THEN** 按钮背景透明、边框 1px 浅蓝、文字浅蓝；hover 时浅蓝底浅加深；与"再学一轮"（`.popRestart`）视觉对称

## MODIFIED Requirements

### Requirement: `.btn.primary` 配色
**改前**：`color: var(--blue-1); background: var(--primary);`
**改后**：`color: #ffffff; background: var(--primary);`
（仅 `color` 一行变化；hover / disabled 行为保留）

### Requirement: `.popOk` 配色
**改前**：
```css
color: #ffffff;
background: linear-gradient(120deg, var(--primary-deep), var(--primary));
```
**改后**（ghost 风格，与 `.popRestart` 视觉对称）：
```css
color: #a9d4ec;            /* 浅蓝 · 固定值，两种主题下都可读 */
background: transparent;
border: 1px solid rgba(169, 212, 236, 0.5);
```
**改后 hover**：
```css
background: rgba(169, 212, 236, 0.12);
border-color: #a9d4ec;
```
**改后 disabled**：沿用现有 `opacity: 0.45; cursor: not-allowed; transform: none;`（已存在，不动）

## REMOVED Requirements
无。

## 备注

- 浅蓝色选 `#a9d4ec`（即 tokens.css 中的 `--sky-hi` 日间值）：与"主色"在色调上一族（都是晴空蓝系），但在明度上明显比 `--primary` 亮，文字落在大面积浅色（弹窗背景为半透白）或深色（页面背景）上时都能保持可读。
- 不用 token 变量名（`var(--sky-hi)`）而用 hex，是因为 `--sky-hi` 在夜间模式下会变成 `#1a2338`（深蓝），与"浅蓝文字"的语义冲突——这正是当前"开始"键踩过的坑。
- 不引入新 token 变量，避免改 `tokens.css` 影响其他组件；本次改动只触及 `index.module.css` 的 1 个 class，scope 干净。

## 验证步骤

1. `cd frontend && npm run build` 通过
2. 启动 dev server，浏览器分别切换日间 / 夜间主题，访问 `/study-timer`：
   - 顶部"开始"按钮文字在两种主题下均为清晰白字
   - 计时结束后弹出的"学习小结"弹窗里"完成"按钮为浅蓝 ghost 风格，与"再学一轮"对称
3. console 无新增 error/warn

# 板块二 · 学科知识浏览 + 错题本（演示用）Spec

## Why
板块二（垂直学科落地）已在 PRD v1.4 中完成详细设计，但后端 API 尚未实现、前端也未开发。
为了让 PRD 评审与下一阶段的"后端实现 + 前端联调"有可触摸的 Demo，需要先在前端以**硬编码数据**落两个页面：
- `/knowledge` 学科知识浏览（知识点树 + 详情）
- `/error-book` 错题本（录入 + 列表 + 复盘/解析）

这两个页面是后续真实接入知识库、错题持久化、AI 解析接口的**骨架与契约对照**，先把 UI 跑通，能用 mock 演示 PRD 评审中"板块二长什么样"，再逐步替换为真实接口。

## What Changes
- 新增前端路由 `/knowledge` 与 `/error-book`，并挂到 AppShell 下。
- 新增 `pages/Knowledge/` 目录：左右分栏（30% 树 + 70% 详情），硬编码知识点数据，掌握度按阈值上色。
- 新增 `pages/ErrorBook/` 目录：学科 Tab + 折叠录入区 + 错题列表 + 复盘展开 + 空状态。
- 新增 `utils/matchKnowledge.ts`：基于硬编码知识库的关键词匹配函数。
- 新增 `services/knowledge.ts`：封装 `POST /api/knowledge-summary` 与 `POST /api/error-parse`。
- 在 `App.jsx` 注册两条新路由（沿用 RequireAuth + AppShell 包裹）。
- 视觉全部走 `styles/tokens.css` / `styles/theme.ts` 的设计令牌，**不写死色值**。
- 新增错题本"搜题 + AI 解析"演示：录入区加关键词匹配、卡片加 AI 解析按钮。

**注**：本轮为演示用，所有数据均为前端硬编码 / localStorage 持久化，**不连接后端**；调用 `/api/knowledge-summary` 与 `/api/error-parse` 仅为满足接口契约演示，未上线路径由后端在下一阶段实现（属已知 TODO）。

## Impact
- 受影响规范：PRD v1.4 第 12 节（板块二）首次有了可演示的 UI 骨架。
- 受影响代码：
  - `frontend/src/App.jsx`（加两条路由）
  - `frontend/src/pages/Knowledge/`（新增）
  - `frontend/src/pages/ErrorBook/`（新增）
  - `frontend/src/utils/matchKnowledge.ts`（新增）
  - `frontend/src/services/knowledge.ts`（新增）

## ADDED Requirements

### Requirement: 学科知识浏览页 `/knowledge`
页面 SHALL 在 RequireAuth + AppShell 之下，仅登录用户可访问。

#### Scenario: 进入页面看到树与默认详情
- **WHEN** 已登录用户访问 `/knowledge`
- **THEN** 左侧默认展开"数学"根节点，子节点（函数/几何/数列）可见；右侧展示首个叶子节点（如"单调性"）的标题（衬线体 24px）、定义、易错点、关联题占位与"查看概念图谱"按钮

#### Scenario: 点击树节点刷新右侧详情
- **WHEN** 用户点击任意知识点节点
- **THEN** 右侧详情区内容切换为该节点的标题/定义/易错点

#### Scenario: 掌握度颜色按阈值
- **WHEN** 节点掌握度 < 40 → 红色；40–70 → 橙色；> 70 → 绿色
- **THEN** 节点右侧百分比与左侧色点颜色与规则一致

#### Scenario: 查看概念图谱按钮
- **WHEN** 用户点击"查看概念图谱"
- **THEN** 弹出 Modal，提示"图谱功能将在 v2.3 上线"，不发生路由跳转

### Requirement: 错题本页 `/error-book`
页面 SHALL 在 RequireAuth + AppShell 之下，仅登录用户可访问。

#### Scenario: 学科切换
- **WHEN** 用户点击"数学/物理/英语"任一 Tab
- **THEN** 列表与录入区的"关联知识点"选项内容随之切换（每个学科有独立 localStorage 命名空间 `errors_{subject}`）

#### Scenario: 默认收起录入区
- **WHEN** 用户首次进入页面
- **THEN** 录入区为折叠状态；点击"+"或"录入错题"按钮后展开

#### Scenario: 录入并保存错题
- **WHEN** 用户填写"题目原文"+"我的错因"+"关联知识点"，点击"保存错题"
- **THEN** 错题以 JSON 写入 `localStorage.errors_{subject}`，表单重置，列表区出现新卡片并自动滚动到列表顶部

#### Scenario: 错题卡片显示
- **WHEN** 错题列表渲染
- **THEN** 每张卡片显示：题目原文（最多 2 行省略）、错因标签（按规则上色：概念不清=橙/计算失误=黄/审题=紫/方法不会=红/其他=灰）、关联知识点标签（淡蓝底深蓝字）、相对时间（如"3 分钟前"）、底部两个按钮"生成复盘"与"AI 解析"

#### Scenario: 生成复盘
- **WHEN** 用户点击"生成复盘"
- **THEN** 按钮进入 loading 状态；调用 `POST /api/knowledge-summary`（body 见任务说明）；成功后在卡片下方展开淡蓝背景区显示返回的 `summary` 文本；失败 toast "复盘生成失败，请稍后再试"

#### Scenario: 空状态
- **WHEN** 当前学科 `errors_{subject}` 为空
- **THEN** 列表区显示淡灰图标 + "还没有错题记录，学完记得来这里记录哦 📝" + "去录入第一道错题"按钮，点击后展开录入区

### Requirement: 错题本"搜题 + AI 解析"演示
错题本页 SHALL 在原录入区与卡片上扩展"关键词匹配知识点"与"AI 解析"两个交互。

#### Scenario: 关键词匹配命中
- **WHEN** 用户在"题目关键词"输入文字，点击"匹配知识点"
- **THEN** 走 `utils/matchKnowledge.ts` 的硬编码关键词表，命中第一条后在按钮下方展示卡片：名称（带掌握度色点 + 百分比）、定义（一行）、易错点（橙色 ⚠ + 文字）、"确认关联此知识点"按钮

#### Scenario: 关键词未命中
- **WHEN** 关键词未命中任一知识点
- **THEN** 显示"未匹配到知识点，请手动选择"并列出全部知识点供点击选择

#### Scenario: AI 解析
- **WHEN** 用户点击错题卡片底部"AI 解析"
- **THEN** 按钮 loading；调用 `POST /api/error-parse`（body 见任务说明）；成功后在卡片下方展开白色卡片显示返回的解析文本（纯文本或 markdown 渲染均可，**不引入新的 UI 库**）；失败 toast "解析生成失败，请稍后重试"

#### Scenario: 匹配到的知识点自动入表单
- **WHEN** 用户在"匹配知识点"区点击"确认关联此知识点"
- **THEN** 该知识点被预填入"关联知识点"字段（用户仍可改）

## MODIFIED Requirements
无（本轮只新增，不改动已有页面与接口契约）。

## REMOVED Requirements
无。

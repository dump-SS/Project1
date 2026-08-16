# 学习状态智能助手 · 前端

板块一 MVP 的 Web 前端。当前已实现「个人数据界面」（`/src/pages/PersonalData`）。

- 需求：`PRD-学习状态智能助手-v1.3.md`
- 接口契约：`docs/openapi.yaml`（唯一生效版本，字段名以此为准）

## 技术栈

| 项 | 选型 | 说明 |
|---|---|---|
| 框架 | React 18 + TypeScript | |
| 构建 | Vite 5 | |
| 组件库 | Ant Design 5 | 主题令牌在 `src/styles/theme.ts` 统一注入 |
| 图表 | Recharts | 折线/面积/环形/仪表盘四类图共用一个库，比 @ant-design/charts 轻很多 |
| 样式 | CSS Modules | 零运行时；颜色走 `theme.ts`，字体走 `var(--font-title)` / `var(--font-body)` |

## 本地启动

```bash
npm install
npm run dev          # http://localhost:5173
```

其他命令：

```bash
npm run typecheck    # 仅类型检查
npm run build        # tsc -b && vite build，产物在 dist/
npm run preview      # 预览生产构建
```

### 联调后端

```bash
cp .env.example .env.local
```

在 `.env.local` 里填 `VITE_API_PROXY_TARGET=http://localhost:8080`（后端实际地址）和 `VITE_API_TOKEN`。
前端代码统一请求 `/api/v1` 相对路径，由 Vite dev server 代理转发，**不需要改任何 service 文件**。

后端没起来时页面不会白屏或报错：每个模块保留占位数据，并在卡片右上角显示「占位数据」标记，悬停可看失败原因。

## 目录结构

```
src/
├── pages/PersonalData/        # 主页面，6 个模块纵向排列
├── components/PersonalData/   # 6 个模块组件 + SectionCard 卡片外壳
├── services/                  # 数据获取，每模块一个文件；http.ts 统一封装
├── hooks/usePanelData.ts      # 「先占位、再请求、失败保留占位」的统一逻辑
├── types/api.ts               # 严格对应 openapi.yaml 的 schema
├── types/view.ts              # 组件消费的视图模型（聚合结果）
├── utils/aggregate.ts         # 日/周/月聚合与格式化
└── styles/                    # theme.ts 设计令牌 + fonts.css 字体变量
```

## 接口对接现状

`openapi.yaml` 里**没有任何统计类接口**，所有日/周/月汇总均由前端基于 `GET /learning-records` 聚合完成，
聚合逻辑集中在 `src/utils/aggregate.ts`，后端若补统计接口可整体替换。

| 模块 | 实际使用的接口 | 状态 |
|---|---|---|
| ① 打卡 | `GET /learning-records?dateFrom&dateTo` | 可用（有记录即视为打卡） |
| ② 时长 | `GET /learning-records` + `GET /plans` | 可用（目标时长借用 `Plan.availableMinutes`） |
| ③ 学科分配 | `GET /learning-records` 按 `subject` 分组 | 可用 |
| ④ 专注度 | `GET /learning-records` 的 `selfReport.focus`<br>+ `GET /assessments/current` 的 `displayText` | 可用（schema 即 1-5，无需换算） |
| ⑤ 日历 | `GET /learning-records` 按月拉取<br>+ `GET /assessments?subject=` 取每日状态标签 | 可用 |
| ⑥ 目标 | `GET /goals?status=active` / `?status=archived` | 可用（终态语义见下） |

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

前端已按「字段存在则用、不存在则退回当前行为」的方式读取（见 `src/services/goals.ts` 的 `toCard`），
所以**后端什么时候上线都行，前端不需要跟着改代码或重新发版**。在此之前 `archived` 统一显示为「已完成」，
完成总结显示为「待生成」。

另有一项低优先级、且有前端兜底方案的缺口：模块①的单日一句话总结。`/summaries` 的区间下限是 3 天，
生成不了单日。可行的替代是复用 `POST /learning-records` 自动创建的 `post_session` 建议
（`GET /recommendations?scene=post_session`，按 `generation.completedAt` 在前端归日），零契约改动。
当前该位置显示为「待生成」。


## 约定

- 不要在组件里硬编码色值，一律从 `src/styles/theme.ts` 引用。
- 不要在组件里直接 `fetch`，统一走 `src/services/`。
- 新增接口字段前先改 `docs/openapi.yaml` —— 它是前后端与 QA 的唯一契约来源。

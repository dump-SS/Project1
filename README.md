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
| ④ 专注度 | `GET /learning-records` 的 `selfReport.focus` | 可用（schema 即 1-5，无需换算） |
| ⑤ 日历 | `GET /learning-records` 按月拉取 | 可用 |
| ⑥ 目标 | `GET /goals?status=active` / `?status=archived` | 可用（状态语义见下） |

### 需要后端补的字段（代码中均已标 `// TODO:`）

1. **单日学习总结**（模块①）——`/summaries` 的区间被限制为 3-31 天，无法生成单日总结。
2. **按日期查询状态标签**（模块⑤）——`/assessments/current` 只返回按学科的当前状态。
   PRD 6.1 规定状态标签必须来自服务端规则层，前端不自行推算。
3. **目标完成总结**（模块⑥）——`Goal` schema 无对应字段。
4. **目标终态语义**（模块⑥）——接口只有 `active` / `archived`，没有「已完成」与「已放弃」的区分。
   当前把 `archived` 显示为「已完成」；若产品要区分两者，需要后端在 `Goal` 上加终态字段。
5. **整体专注度评语**（模块④）——需求要求 AI 生成，现为按分数段匹配的硬编码文案。

## 约定

- 不要在组件里硬编码色值，一律从 `src/styles/theme.ts` 引用。
- 不要在组件里直接 `fetch`，统一走 `src/services/`。
- 新增接口字段前先改 `docs/openapi.yaml` —— 它是前后端与 QA 的唯一契约来源。

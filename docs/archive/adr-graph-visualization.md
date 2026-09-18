# ADR：板块二概念图谱可视化选型

- 状态：已决策
- 日期：2026-08-24
- 依据：`docs/module2-3-development-plan.md` §6 2.3-1、PRD 12.3.3

## 决策

选择 **vis-network**（v2.3 起引入前端依赖）；备选 D3。

| 维度 | vis-network | D3 |
|---|---|---|
| 力导向图内置 | ✅ 自带 physics/布局/缩放/拖拽，开箱即用 | ❌ 需手写力导向 + tick 渲染 |
| 500 节点交互成本 | 低（Canvas 渲染，事件模型现成） | 高（SVG + 手动事件与缩放） |
| 定制粒度 | 中（样式可配，深层定制受限） | 高（完全自定义） |
| 与 React 集成 | 有社区封装，也可直接操作实例 | 需手动管理生命周期 |

**理由**：v2.3 目标是「图能看、节点色阶=掌握度、点选联动详情」，vis-network 的
内置 physics + Canvas 渲染在 500 节点规模上集成成本远低于 D3；深度定制需求
（如自定义边绘制）当前不存在。若后续需要高度定制再评估迁移 D3。

## 性能目标（PRD 12.9）

- 500 节点力导向初渲染 < 1s（Canvas，physics 用 barnesHut）
- 节点按章节懒加载（`GET /knowledge/subjects/{code}/graph` 返回全图，前端按需展开）
- mastery 色阶：红 <0.4 / 橙 0.4-0.7 / 绿 >0.7（与现有 Knowledge 页一致）

## 影响

- 前端新增依赖 `vis-network`（package.json）
- 新增页面 `frontend/src/pages/Knowledge/Graph.tsx`（或 Knowledge 内嵌），数据源
  `GET /knowledge/subjects/{code}/graph`（后端 v2.1 已实现树形占位，v2.3 补全关系边）

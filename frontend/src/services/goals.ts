/**
 * 模块⑥ 短/长期目标及历史完成情况 —— 数据获取。
 *
 * 接口映射说明：
 * - 这是 6 个模块里唯一能直接对上的：`GET /api/v1/goals?status=`（openapi.yaml 2.2 listGoals）。
 * - 但状态枚举与需求对不齐：接口只有 `active` / `archived` 两种取值，
 *   没有需求里写的「已完成 / 已放弃」。openapi.yaml 10.6 说明「归档代替删除，保留历史数据供复盘引用」。
 *   已向后端提出纯增量改动：给 Goal 加可选的 `outcome` 与 `completionNote`。
 *   本文件已按「字段存在则用、不存在则退回当前行为」的方式读取，
 *   后端上线后前端无需任何改动即可自动生效，因此不构成并行开发的阻塞点。
 * - 进度百分比取 GoalProgress.ratio（0-1），换算成 0-100。
 * - 写入侧三个动作（create / update / archive）均与契约一一对应：
 *   `POST /goals`、`PATCH /goals/{goalId}`、`PATCH /goals/{goalId} { status: 'archived' }`。
 *   契约里没有独立 DELETE；归档即"软删除"，保留历史供复盘引用。
 */

import { apiGetAllPages, apiPatch, apiPost } from './http';
import type { Goal, GoalCreate, GoalOutcome, GoalSummary, GoalUpdate } from '@/types/api';
import type { GoalCard, GoalPanel } from '@/types/view';
import { subjectLabels } from '@/styles/theme';

/**
 * 目标树与考试引用（openapi v1.7.1 · D6 / D29 / D49）。
 *
 * ⚠️ 这三个字段在契约里已冻结，但 `types/api.ts` 归 X1 管（X0 定字段 / X1 管导出），
 * C 板块不动手，所以先定义在这里；X1 收口时把它们并进 `types/api.ts` 即可。
 *
 * - `parentGoalId`：父目标。目标表达意愿，考试表达事实，两者不混；
 *   父子树表达的是「长期目标 → 多个短期子目标」的**从属关系**。
 * - `examId` + `targetScore`：这次考试想考到多少分。**目标只存意愿，分数结果存在 exams 表里**。
 */
export interface GoalExtras {
  parentGoalId?: string | null;
  examId?: string | null;
  targetScore?: number | null;
}

export type GoalCreateInput = GoalCreate & GoalExtras;
export type GoalUpdateInput = GoalUpdate & GoalExtras;
export type GoalCardWithExtras = GoalCard & GoalExtras;
/** 树节点：卡片 + 子目标（由 buildGoalTree 组装，后端返回的是扁平列表） */
export type GoalTreeNode = GoalCardWithExtras & { children?: GoalTreeNode[] };
export type GoalPanelWithExtras = Omit<GoalPanel, 'active' | 'finished'> & {
  active: GoalCardWithExtras[];
  finished: GoalCardWithExtras[];
};

const TYPE_LABELS: Record<GoalSummary['type'], string> = {
  short_term: '短期',
  long_term: '长期',
};

const OUTCOME_LABELS: Record<GoalOutcome, string> = {
  achieved: '已达成',
  abandoned: '已放弃',
  expired: '已过期',
};

/**
 * 归档目标的展示文案。
 * outcome 字段补齐前，所有 archived 统一显示「已完成」——这是当前契约能支持的最大精度，
 * 不猜测用户到底是达成还是放弃。
 */
function resolveStatusLabel(status: GoalSummary['status'], outcome: GoalOutcome | null): string {
  if (status === 'active') return '进行中';
  return outcome ? OUTCOME_LABELS[outcome] : '已完成';
}

function toCard(goal: GoalSummary & Partial<GoalExtras>): GoalCardWithExtras {
  const outcome = goal.outcome ?? null;

  return {
    goalId: goal.goalId,
    title: goal.title,
    type: goal.type,
    typeLabel: TYPE_LABELS[goal.type],
    subject: goal.subject,
    subjectLabel: subjectLabels[goal.subject] ?? goal.subject,
    targetDate: goal.targetDate,
    status: goal.status,
    outcome,
    statusLabel: resolveStatusLabel(goal.status, outcome),
    percent: Math.round((goal.progress?.ratio ?? 0) * 100),
    plannedTasks: goal.progress?.plannedTasks ?? 0,
    completedTasks: goal.progress?.completedTasks ?? 0,
    completionNote: goal.completionNote ?? null,
    // 目标树与考试引用（D6/D49）
    parentGoalId: goal.parentGoalId ?? null,
    examId: goal.examId ?? null,
    targetScore: goal.targetScore ?? null,
  };
}

export async function fetchGoals(signal?: AbortSignal): Promise<GoalPanelWithExtras> {
  // 用 apiGetAllPages 翻页取全部，与其余 service 一致；
  // 之前用 apiGet 只取第 1 页，归档目标超过 50 条时后续会被静默丢弃。
  const [activeItems, archivedItems] = await Promise.all([
    apiGetAllPages<GoalSummary & Partial<GoalExtras>>('/goals', { status: 'active' }, signal),
    apiGetAllPages<GoalSummary & Partial<GoalExtras>>('/goals', { status: 'archived' }, signal),
  ]);

  return {
    active: activeItems.map(toCard),
    finished: archivedItems.map(toCard),
  };
}

/**
 * 把扁平列表组装成**父子树**（D6/D29）。
 *
 * 两条兜底很重要：
 * - 父目标**不在 active 列表里**（已归档 / 跨页丢失）→ 子目标按顶层处理，
 *   不能因为找不到父就把整条子树丢掉；
 * - 历史脏数据可能造成**环**，组装时用 visited 集合断环，避免渲染时死循环。
 */
export function buildGoalTree(items: GoalCardWithExtras[]): GoalTreeNode[] {
  const byId = new Map(items.map((g) => [g.goalId, g]));
  const childrenOf = new Map<string | null, GoalCardWithExtras[]>();

  for (const goal of items) {
    const parentId = goal.parentGoalId && byId.has(goal.parentGoalId) ? goal.parentGoalId : null;
    const bucket = childrenOf.get(parentId) ?? [];
    bucket.push(goal);
    childrenOf.set(parentId, bucket);
  }

  const visited = new Set<string>();
  const attach = (goal: GoalCardWithExtras): GoalTreeNode => {
    visited.add(goal.goalId);
    const kids = (childrenOf.get(goal.goalId) ?? [])
      .filter((k) => !visited.has(k.goalId)) // 断环
      .map(attach);
    return { ...goal, children: kids };
  };

  const roots = childrenOf.get(null) ?? [];

  // ⚠️ 兜住「互相指着对方」的环：环里的节点**没有任何根可达**，
  // 只按 roots 渲染会让整条环从列表里消失——用户会以为目标被删了。
  // 所以把不可达节点提升为顶层，至少保证它可见、可编辑（编辑时又能把环解开）。
  const reachable = new Set<string>();
  const mark = (nodes: GoalCardWithExtras[]) => {
    for (const n of nodes) {
      if (reachable.has(n.goalId)) continue; // 环不会无限递归
      reachable.add(n.goalId);
      mark(childrenOf.get(n.goalId) ?? []);
    }
  };
  mark(roots);
  const promoted = items.filter((g) => !reachable.has(g.goalId));

  // 逐个 attach，跳过已渲染过的（提升的节点可能同时是另一个提升节点的子节点）
  const out: GoalTreeNode[] = [];
  for (const g of [...roots, ...promoted]) {
    if (visited.has(g.goalId)) continue;
    out.push(attach(g));
  }
  return out;
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderGoals(): GoalPanel {
  const active: GoalCard[] = [
    {
      goalId: 'g_5501',
      title: '两周后期中考试数学 120+',
      type: 'short_term',
      typeLabel: '短期',
      subject: 'SX',
      subjectLabel: '数学',
      targetDate: '2026-08-30',
      status: 'active',
      outcome: null,
      statusLabel: '进行中',
      percent: 58,
      plannedTasks: 12,
      completedTasks: 7,
      completionNote: null,
    },
    {
      goalId: 'g_5502',
      title: '高考英语稳定在 135 分区间',
      type: 'long_term',
      typeLabel: '长期',
      subject: 'YY',
      subjectLabel: '英语',
      targetDate: '2027-06-08',
      status: 'active',
      outcome: null,
      statusLabel: '进行中',
      percent: 24,
      plannedTasks: 50,
      completedTasks: 12,
      completionNote: null,
    },
    {
      goalId: 'g_5503',
      title: '本周弄懂电磁感应这一章',
      type: 'short_term',
      typeLabel: '短期',
      subject: 'WL',
      subjectLabel: '物理',
      targetDate: '2026-08-22',
      status: 'active',
      outcome: null,
      statusLabel: '进行中',
      percent: 80,
      plannedTasks: 5,
      completedTasks: 4,
      completionNote: null,
    },
  ];

  const finished: GoalCard[] = [
    {
      goalId: 'g_5490',
      title: '暑假补完函数与数列两章',
      type: 'short_term',
      typeLabel: '短期',
      subject: 'SX',
      subjectLabel: '数学',
      targetDate: '2026-08-10',
      status: 'archived',
      outcome: 'achieved',
      statusLabel: '已达成',
      percent: 100,
      plannedTasks: 16,
      completedTasks: 16,
      completionNote: '达成！比预期多花了 3 天，但正确率超预期。',
    },
    {
      goalId: 'g_5488',
      title: '每天背 30 个单词，坚持一个月',
      type: 'short_term',
      typeLabel: '短期',
      subject: 'YY',
      subjectLabel: '英语',
      targetDate: '2026-07-31',
      status: 'archived',
      outcome: 'abandoned',
      statusLabel: '已放弃',
      percent: 93,
      plannedTasks: 30,
      completedTasks: 28,
      completionNote: '最后两天没顶住，但前 28 天是实打实的，下次把目标定小一点。',
    },
  ];

  return { active, finished };
}

/* ---------- 写入：create / update / archive ---------- */

/**
 * 创建学习目标。对应 `POST /api/v1/goals`（openapi.yaml createGoal）。
 * 必填 type / subject / title；description / targetDate / templateId 可选，
 * 另有 parentGoalId / examId / targetScore（D6 / D49）。
 * 成功后服务端返回完整 Goal 对象，调用方可立即塞进本地列表。
 */
export function createGoal(payload: GoalCreateInput, signal?: AbortSignal): Promise<Goal> {
  return apiPost<Goal>('/goals', payload, signal);
}

/**
 * 更新目标字段。对应 `PATCH /api/v1/goals/{goalId}`（openapi.yaml updateGoal）。
 * 至少传一项；title ≤ 50、description ≤ 200。
 * 成功后服务端返回完整 Goal（含最新的 progress）。
 *
 * ⚠️ **「不传」与「传 null」语义不同**：`parentGoalId: null` = 提升为顶层目标
 * （与「不传=不动」区分），调用方想清空关联必须**显式**传 null。
 */
export function updateGoal(
  goalId: string,
  patch: GoalUpdateInput,
  signal?: AbortSignal,
): Promise<Goal> {
  return apiPatch<Goal>(`/goals/${encodeURIComponent(goalId)}`, patch, signal);
}

/**
 * 归档目标（"软删除"）。契约里没有独立 DELETE：归档保留历史供复盘引用。
 * 实现上仍是 `PATCH /api/v1/goals/{goalId}`，只把 status 写成 archived。
 */
export function archiveGoal(goalId: string, signal?: AbortSignal): Promise<Goal> {
  return updateGoal(goalId, { status: 'archived' }, signal);
}

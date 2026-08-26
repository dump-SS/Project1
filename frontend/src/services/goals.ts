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

function toCard(goal: GoalSummary): GoalCard {
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
  };
}

export async function fetchGoals(signal?: AbortSignal): Promise<GoalPanel> {
  // 用 apiGetAllPages 翻页取全部，与其余 service 一致；
  // 之前用 apiGet 只取第 1 页，归档目标超过 50 条时后续会被静默丢弃。
  const [activeItems, archivedItems] = await Promise.all([
    apiGetAllPages<GoalSummary>('/goals', { status: 'active' }, signal),
    apiGetAllPages<GoalSummary>('/goals', { status: 'archived' }, signal),
  ]);

  return {
    active: activeItems.map(toCard),
    finished: archivedItems.map(toCard),
  };
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
 * 必填 type / subject / title；description / targetDate / templateId 可选。
 * 成功后服务端返回完整 Goal 对象，调用方可立即塞进本地列表。
 */
export function createGoal(payload: GoalCreate, signal?: AbortSignal): Promise<Goal> {
  return apiPost<Goal>('/goals', payload, signal);
}

/**
 * 更新目标字段。对应 `PATCH /api/v1/goals/{goalId}`（openapi.yaml updateGoal）。
 * 至少传一项；title ≤ 50、description ≤ 200。
 * 成功后服务端返回完整 Goal（含最新的 progress）。
 */
export function updateGoal(
  goalId: string,
  patch: GoalUpdate,
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

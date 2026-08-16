/**
 * 模块⑥ 短/长期目标及历史完成情况 —— 数据获取。
 *
 * 接口映射说明：
 * - 这是 6 个模块里唯一能直接对上的：`GET /api/v1/goals?status=`（openapi.yaml 2.2 listGoals）。
 * - 但状态枚举与需求对不齐：接口只有 `active` / `archived` 两种取值，
 *   没有需求里写的「已完成 / 已放弃」。openapi.yaml 10.6 说明「归档代替删除，保留历史数据供复盘引用」，
 *   因此这里把 archived 映射为 UI 上的「已完成」，且在页面上如实注明。
 *   若产品确实需要区分「完成」与「放弃」，需要后端在 Goal 上补一个终态字段，不能靠前端猜。
 * - 进度百分比取 GoalProgress.ratio（0-1），换算成 0-100。
 * - 「完成总结」：Goal schema 里没有任何对应字段，故为 null。
 */

import { apiGet } from './http';
import type { GoalList, GoalSummary } from '@/types/api';
import type { GoalCard, GoalPanel } from '@/types/view';
import { subjectLabels } from '@/styles/theme';

const TYPE_LABELS: Record<GoalSummary['type'], string> = {
  short_term: '短期',
  long_term: '长期',
};

const STATUS_LABELS: Record<GoalSummary['status'], string> = {
  active: '进行中',
  archived: '已完成',
};

function toCard(goal: GoalSummary): GoalCard {
  return {
    goalId: goal.goalId,
    title: goal.title,
    type: goal.type,
    typeLabel: TYPE_LABELS[goal.type],
    subject: goal.subject,
    subjectLabel: subjectLabels[goal.subject] ?? goal.subject,
    targetDate: goal.targetDate,
    status: goal.status,
    statusLabel: STATUS_LABELS[goal.status],
    percent: Math.round((goal.progress?.ratio ?? 0) * 100),
    plannedTasks: goal.progress?.plannedTasks ?? 0,
    completedTasks: goal.progress?.completedTasks ?? 0,
    // TODO: 「完成总结」字段接口待后端提供，Goal schema 中暂无对应字段。
    completionNote: null,
  };
}

export async function fetchGoals(signal?: AbortSignal): Promise<GoalPanel> {
  const [activeList, archivedList] = await Promise.all([
    apiGet<GoalList>('/goals', { status: 'active', pageSize: 50 }, signal),
    apiGet<GoalList>('/goals', { status: 'archived', pageSize: 50 }, signal),
  ]);

  return {
    active: (activeList.items ?? []).map(toCard),
    finished: (archivedList.items ?? []).map(toCard),
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
      subject: 'math',
      subjectLabel: '数学',
      targetDate: '2026-08-30',
      status: 'active',
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
      subject: 'english',
      subjectLabel: '英语',
      targetDate: '2027-06-08',
      status: 'active',
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
      subject: 'physics',
      subjectLabel: '物理',
      targetDate: '2026-08-22',
      status: 'active',
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
      subject: 'math',
      subjectLabel: '数学',
      targetDate: '2026-08-10',
      status: 'archived',
      statusLabel: '已完成',
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
      subject: 'english',
      subjectLabel: '英语',
      targetDate: '2026-07-31',
      status: 'archived',
      statusLabel: '已完成',
      percent: 100,
      plannedTasks: 30,
      completedTasks: 28,
      completionNote: '中间断了两天，后面补回来了，节奏比数量更重要。',
    },
  ];

  return { active, finished };
}

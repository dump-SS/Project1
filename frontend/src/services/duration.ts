/**
 * 模块② 学习时长 —— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/stats/duration` 在 openapi.yaml 中不存在，且全文没有任何统计类接口。
 *   实际使用 `GET /api/v1/learning-records`（openapi.yaml 4.2），按 startedAt 归日累加 durationMinutes。
 * - 目标时长：借用 `GET /api/v1/plans`（openapi.yaml 3.2）当日计划的 availableMinutes，
 *   它的语义是「本次可用学习时间」，是现有契约里最接近「目标时长」的字段。
 *   若当天没有计划则返回 null，UI 隐藏进度条而不是编一个默认目标值。
 */

import { apiGetAllPages } from './http';
import type { LearningRecord, Plan } from '@/types/api';
import type { DurationPanel, DurationPoint } from '@/types/view';
import {
  DATE_FORMAT,
  dayjs,
  groupRecordsByDate,
  lastNDates,
  sumMinutes,
  toHours,
} from '@/utils/aggregate';

const DAYS = 7;

export async function fetchDuration(signal?: AbortSignal): Promise<DurationPanel> {
  const today = dayjs();
  const dateFrom = today.subtract(DAYS - 1, 'day').format(DATE_FORMAT);
  const dateTo = today.format(DATE_FORMAT);
  const todayKey = today.format(DATE_FORMAT);

  const [records, plans] = await Promise.all([
    apiGetAllPages<LearningRecord>('/learning-records', { dateFrom, dateTo }, signal),
    // 计划接口失败不应拖垮整个模块，目标时长本就是可选展示
    apiGetAllPages<Plan>('/plans', { dateFrom: todayKey, dateTo: todayKey }, signal).catch(
      () => [] as Plan[],
    ),
  ]);

  const byDate = groupRecordsByDate(records);

  const trend: DurationPoint[] = lastNDates(DAYS, today).map((date) => ({
    date,
    dayLabel: dayjs(date).format('M/D'),
    hours: toHours(sumMinutes(byDate[date] ?? [])),
  }));

  const todayPlan = plans.find((plan) => plan.planDate === todayKey);

  return {
    todayMinutes: sumMinutes(byDate[todayKey] ?? []),
    targetMinutes: todayPlan?.availableMinutes ?? null,
    trend,
  };
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderDuration(): DurationPanel {
  const hoursPreset = [1.6, 2.2, 0, 1.0, 2.4, 1.3, 2.5];

  return {
    todayMinutes: 150,
    targetMinutes: 180,
    trend: lastNDates(7).map((date, index) => ({
      date,
      dayLabel: dayjs(date).format('M/D'),
      hours: hoursPreset[index],
    })),
  };
}

/**
 * 聚合与格式化工具。
 *
 * openapi.yaml 只提供原始 LearningRecord，没有任何统计类接口，
 * 因此日/周/月的汇总全部在前端完成，逻辑集中在这里便于后端补统计接口后整体替换。
 */

import dayjs, { type Dayjs } from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import type { LearningRecord, Subject } from '@/types/api';

dayjs.extend(isoWeek);

export const DATE_FORMAT = 'YYYY-MM-DD';

const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

/** 取某个日期的星期中文label */
export function weekdayLabel(date: Dayjs): string {
  return WEEKDAY_LABELS[date.day()];
}

/** 最近 n 天的日期串，含今天，按时间正序 */
export function lastNDates(n: number, endDate: Dayjs = dayjs()): string[] {
  return Array.from({ length: n }, (_, index) =>
    endDate.subtract(n - 1 - index, 'day').format(DATE_FORMAT),
  );
}

/** 从 ISO 时间串取出归属日期（YYYY-MM-DD） */
export function toDateKey(isoDateTime: string): string {
  return dayjs(isoDateTime).format(DATE_FORMAT);
}

/** 通用分组 */
export function groupBy<T, K extends string>(list: T[], keyOf: (item: T) => K): Record<K, T[]> {
  return list.reduce(
    (acc, item) => {
      const key = keyOf(item);
      (acc[key] ??= []).push(item);
      return acc;
    },
    {} as Record<K, T[]>,
  );
}

/** 学习记录按自然日分组，key 为 startedAt 所在日期 */
export function groupRecordsByDate(records: LearningRecord[]): Record<string, LearningRecord[]> {
  return groupBy(records, (record) => toDateKey(record.startedAt));
}

/** 学习记录按学科分组 */
export function groupRecordsBySubject(records: LearningRecord[]): Record<string, LearningRecord[]> {
  return groupBy(records, (record) => record.subject as Subject);
}

/** 时长求和（分钟） */
export function sumMinutes(records: LearningRecord[]): number {
  return records.reduce((total, record) => total + (record.durationMinutes ?? 0), 0);
}

/** 平均值，空数组返回 null 而不是 0，避免「没数据」被画成「得分 0」 */
export function average(values: number[]): number | null {
  if (values.length === 0) return null;
  const sum = values.reduce((acc, value) => acc + value, 0);
  return sum / values.length;
}

/**
 * 按时长加权的平均专注度。
 * 学 5 分钟和学 60 分钟的自评不该等权，用时长加权更接近真实体感。
 */
export function weightedFocus(records: LearningRecord[]): number | null {
  const valid = records.filter((record) => typeof record.selfReport?.focus === 'number');
  if (valid.length === 0) return null;

  const totalWeight = valid.reduce((acc, record) => acc + Math.max(record.durationMinutes, 1), 0);
  const weightedSum = valid.reduce(
    (acc, record) => acc + record.selfReport.focus * Math.max(record.durationMinutes, 1),
    0,
  );
  return weightedSum / totalWeight;
}

/** 分钟转「2.5h」；不足 1 小时显示「45min」 */
export function formatDuration(minutes: number): string {
  if (minutes <= 0) return '0h';
  if (minutes < 60) return `${Math.round(minutes)}min`;
  return `${(minutes / 60).toFixed(1)}h`;
}

/** 分钟转小时数值，保留一位小数，供图表 Y 轴使用 */
export function toHours(minutes: number): number {
  return Math.round((minutes / 60) * 10) / 10;
}

/** 保留一位小数 */
export function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

export { dayjs };

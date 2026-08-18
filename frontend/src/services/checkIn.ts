/**
 * 模块① 学习情况（日常打卡）及总结 —— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/records/history` 在 openapi.yaml 中不存在。
 *   实际使用 `GET /api/v1/learning-records?dateFrom&dateTo`（openapi.yaml 4.2 listLearningRecords），
 *   「某天是否打卡」由该天是否存在学习记录推导，不需要额外的打卡接口。
 * - 每日一句话总结：调后端新增的 `GET /api/v1/daily-summary?date=YYYY-MM-DD`，
 *   该接口与 /summaries（3-31 天复盘）解耦，专门覆盖单日场景。
 *   LLM 失败/无数据时后端会返回兜底句，前端无需再做兜底。
 */

import { apiGet, apiGetAllPages } from './http';
import type { LearningRecord } from '@/types/api';
import type { CheckInDay, CheckInPanel } from '@/types/view';
import {
  DATE_FORMAT,
  dayjs,
  groupRecordsByDate,
  lastNDates,
  sumMinutes,
  weekdayLabel,
} from '@/utils/aggregate';

const DAYS = 7;

interface DailySummaryResponse {
  date: string;
  summary: string;
}

/** 拉取某天的一句话总结（后端 /daily-summary，无数据时也返回兜底句）。 */
export async function fetchDaySummary(date: string, signal?: AbortSignal): Promise<string> {
  try {
    const res = await apiGet<DailySummaryResponse>(`/daily-summary`, { date }, signal);
    return res.summary;
  } catch {
    // 任意错误（网络/401/500）都返回空串，让 UI 走"无总结"占位
    return '';
  }
}

/** 拉取最近 7 天打卡情况 */
export async function fetchCheckIn(signal?: AbortSignal): Promise<CheckInPanel> {
  const today = dayjs();
  const dateFrom = today.subtract(DAYS - 1, 'day').format(DATE_FORMAT);
  const dateTo = today.format(DATE_FORMAT);

  const records = await apiGetAllPages<LearningRecord>(
    '/learning-records',
    { dateFrom, dateTo },
    signal,
  );

  const byDate = groupRecordsByDate(records);
  const todayKey = today.format(DATE_FORMAT);

  // 每个有打卡的日期并行拉总结
  const days: CheckInDay[] = await Promise.all(
    lastNDates(DAYS, today).map(async (date) => {
      const dayRecords = byDate[date] ?? [];
      const summary = dayRecords.length > 0 ? await fetchDaySummary(date, signal) : null;
      return {
        date,
        weekdayLabel: weekdayLabel(dayjs(date)),
        dayLabel: dayjs(date).format('M/D'),
        isToday: date === todayKey,
        checked: dayRecords.length > 0,
        totalMinutes: sumMinutes(dayRecords),
        recordCount: dayRecords.length,
        subjects: Array.from(new Set(dayRecords.map((record) => record.subject))),
        summary: summary || null,
      };
    }),
  );

  return {
    days,
    checkedCount: days.filter((day) => day.checked).length,
    totalDays: DAYS,
  };
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderCheckIn(): CheckInPanel {
  const today = dayjs();
  const preset = [
    { checked: true, minutes: 95, summary: '完成了函数专项，状态平稳。' },
    { checked: true, minutes: 130, summary: '英语听力连着做了两套，耳朵有点累。' },
    { checked: false, minutes: 0, summary: null },
    { checked: true, minutes: 60, summary: '只补了错题本，量不大但心里踏实。' },
    { checked: true, minutes: 145, summary: '数列那章终于串起来了。' },
    { checked: true, minutes: 80, summary: '晚自习前刷了一组选择，手感回来了。' },
    { checked: true, minutes: 150, summary: '函数图像和单词各占一半，节奏还算稳。' },
  ];

  const days: CheckInDay[] = lastNDates(7, today).map((date, index) => {
    const item = preset[index];
    return {
      date,
      weekdayLabel: weekdayLabel(dayjs(date)),
      dayLabel: dayjs(date).format('M/D'),
      isToday: date === today.format(DATE_FORMAT),
      checked: item.checked,
      totalMinutes: item.minutes,
      recordCount: item.checked ? 2 : 0,
      subjects: item.checked ? ['math', 'english'] : [],
      summary: item.summary,
    };
  });

  return {
    days,
    checkedCount: days.filter((day) => day.checked).length,
    totalDays: 7,
  };
}

/**
 * 模块⑤ 内置日历 —— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/calendar/marks` 在 openapi.yaml 中不存在。
 *   实际使用 `GET /api/v1/learning-records?dateFrom&dateTo`（openapi.yaml 4.2）按月拉取，
 *   有记录的日期即为需要打点的日期，当天摘要由同一份数据在前端聚合，不需要二次请求。
 * - 当天的「状态如何」：PRD 6.1 明确规定状态标签属于服务端规则层产物，
 *   「所有对用户可见的数字和结论性标签都来自规则层，模型不得覆盖」，
 *   因此前端不自行推算 stateLabel。openapi.yaml 的 /assessments/current 只返回按学科的当前状态、
 *   不支持按日期查询历史标签，故此字段暂为 null。
 */

import { apiGetAllPages } from './http';
import type { LearningRecord, Subject } from '@/types/api';
import type { CalendarDayDetail, CalendarPanel, CalendarSubjectStat } from '@/types/view';
import { subjectLabels } from '@/styles/theme';
import {
  DATE_FORMAT,
  average,
  dayjs,
  groupRecordsByDate,
  groupRecordsBySubject,
  round1,
  sumMinutes,
} from '@/utils/aggregate';

function buildDayDetail(date: string, records: LearningRecord[]): CalendarDayDetail {
  const bySubject = groupRecordsBySubject(records);

  const subjects: CalendarSubjectStat[] = Object.entries(bySubject)
    .map(([subject, subjectRecords]) => ({
      subject: subject as Subject,
      label: subjectLabels[subject as Subject] ?? subject,
      minutes: sumMinutes(subjectRecords),
    }))
    .sort((a, b) => b.minutes - a.minutes);

  const focusAvg = average(records.map((record) => record.selfReport.focus));
  const fatigueAvg = average(records.map((record) => record.selfReport.fatigue));

  return {
    date,
    totalMinutes: sumMinutes(records),
    recordCount: records.length,
    subjects,
    focusAvg: focusAvg === null ? null : round1(focusAvg),
    fatigueAvg: fatigueAvg === null ? null : round1(fatigueAvg),
    // TODO: 按日期查询状态标签的接口待后端提供；前端不自行推算（PRD 6.1）。
    stateLabel: null,
  };
}

/** 拉取指定月份（YYYY-MM）的日历打点与每日摘要 */
export async function fetchCalendar(month: string, signal?: AbortSignal): Promise<CalendarPanel> {
  const start = dayjs(`${month}-01`);
  const records = await apiGetAllPages<LearningRecord>(
    '/learning-records',
    {
      dateFrom: start.startOf('month').format(DATE_FORMAT),
      dateTo: start.endOf('month').format(DATE_FORMAT),
    },
    signal,
  );

  const byDate = groupRecordsByDate(records);
  const marks: Record<string, CalendarDayDetail> = {};
  for (const [date, dayRecords] of Object.entries(byDate)) {
    marks[date] = buildDayDetail(date, dayRecords);
  }

  return { marks, month };
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderCalendar(month: string): CalendarPanel {
  const start = dayjs(`${month}-01`);
  const marks: Record<string, CalendarDayDetail> = {};

  const preset = [
    { offset: 1, minutes: 95, focus: 4.0, fatigue: 2.0, subjects: ['math', 'english'] },
    { offset: 2, minutes: 130, focus: 3.5, fatigue: 3.0, subjects: ['math'] },
    { offset: 4, minutes: 60, focus: 4.5, fatigue: 2.0, subjects: ['physics'] },
    { offset: 7, minutes: 145, focus: 3.0, fatigue: 4.0, subjects: ['math', 'chinese'] },
    { offset: 8, minutes: 80, focus: 4.2, fatigue: 2.5, subjects: ['english'] },
    { offset: 11, minutes: 110, focus: 3.8, fatigue: 3.0, subjects: ['math', 'physics'] },
    { offset: 14, minutes: 55, focus: 2.8, fatigue: 4.5, subjects: ['chemistry'] },
    { offset: 15, minutes: 165, focus: 4.6, fatigue: 2.0, subjects: ['math', 'english'] },
  ];

  for (const item of preset) {
    const date = start.add(item.offset, 'day');
    if (date.month() !== start.month()) continue;

    const key = date.format(DATE_FORMAT);
    marks[key] = {
      date: key,
      totalMinutes: item.minutes,
      recordCount: item.subjects.length,
      subjects: item.subjects.map((subject) => ({
        subject: subject as Subject,
        label: subjectLabels[subject as Subject],
        minutes: Math.round(item.minutes / item.subjects.length),
      })),
      focusAvg: item.focus,
      fatigueAvg: item.fatigue,
      stateLabel: null,
    };
  }

  return { marks, month };
}

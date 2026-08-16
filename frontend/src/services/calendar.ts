/**
 * 模块⑤ 内置日历 —— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/calendar/marks` 在 openapi.yaml 中不存在。
 *   实际使用 `GET /api/v1/learning-records?dateFrom&dateTo`（openapi.yaml 4.2）按月拉取，
 *   有记录的日期即为需要打点的日期，当天的时长/自评摘要由同一份数据在前端聚合。
 * - 当天的「状态如何」：使用 `GET /api/v1/assessments?subject=&dateFrom&dateTo`（openapi.yaml 5.2），
 *   它按日期返回 stateLabel / windowScore / trend。该接口 subject 为必填且按单学科查询，
 *   PRD 5.2 明确「不做跨学科的加权综合」，所以这里**按学科分别展示标签，不合并成单一的当日标签**。
 *   标签一律取自服务端规则层，前端不自行推算（PRD 6.1）。
 */

import { apiGet, apiGetAllPages } from './http';
import type { AssessmentHistory, LearningRecord, StateLabel, Subject } from '@/types/api';
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

/** date -> subject -> stateLabel */
type LabelIndex = Record<string, Partial<Record<Subject, StateLabel>>>;

/**
 * 按学科拉取状态历史并索引成 date -> subject -> stateLabel。
 * 只查当月实际出现过的学科，避免为没学过的科目发无谓请求。
 * 单个学科失败不影响其他学科，也不影响日历主体渲染。
 */
async function fetchLabelIndex(
  subjects: Subject[],
  dateFrom: string,
  dateTo: string,
  signal?: AbortSignal,
): Promise<LabelIndex> {
  const results = await Promise.all(
    subjects.map((subject) =>
      apiGet<AssessmentHistory>('/assessments', { subject, dateFrom, dateTo }, signal).catch(
        () => null,
      ),
    ),
  );

  const index: LabelIndex = {};
  for (const history of results) {
    if (!history) continue;
    for (const point of history.items ?? []) {
      (index[point.date] ??= {})[history.subject] = point.stateLabel;
    }
  }
  return index;
}

function buildDayDetail(
  date: string,
  records: LearningRecord[],
  labelIndex: LabelIndex,
): CalendarDayDetail {
  const bySubject = groupRecordsBySubject(records);
  const labelsOfDay = labelIndex[date] ?? {};

  const subjects: CalendarSubjectStat[] = Object.entries(bySubject)
    .map(([subject, subjectRecords]) => ({
      subject: subject as Subject,
      label: subjectLabels[subject as Subject] ?? subject,
      minutes: sumMinutes(subjectRecords),
      stateLabel: labelsOfDay[subject as Subject] ?? null,
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
  };
}

/** 拉取指定月份（YYYY-MM）的日历打点与每日摘要 */
export async function fetchCalendar(month: string, signal?: AbortSignal): Promise<CalendarPanel> {
  const start = dayjs(`${month}-01`);
  const dateFrom = start.startOf('month').format(DATE_FORMAT);
  const dateTo = start.endOf('month').format(DATE_FORMAT);

  const records = await apiGetAllPages<LearningRecord>(
    '/learning-records',
    { dateFrom, dateTo },
    signal,
  );

  const presentSubjects = Array.from(new Set(records.map((record) => record.subject)));
  const labelIndex =
    presentSubjects.length > 0
      ? await fetchLabelIndex(presentSubjects, dateFrom, dateTo, signal)
      : {};

  const byDate = groupRecordsByDate(records);
  const marks: Record<string, CalendarDayDetail> = {};
  for (const [date, dayRecords] of Object.entries(byDate)) {
    marks[date] = buildDayDetail(date, dayRecords, labelIndex);
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

  const preset: Array<{
    offset: number;
    minutes: number;
    focus: number;
    fatigue: number;
    subjects: Array<[Subject, StateLabel]>;
  }> = [
    { offset: 1, minutes: 95, focus: 4.0, fatigue: 2.0, subjects: [['math', 'efficient_stable'], ['english', 'fluctuating_up']] },
    { offset: 2, minutes: 130, focus: 3.5, fatigue: 3.0, subjects: [['math', 'efficient_stable']] },
    { offset: 4, minutes: 60, focus: 4.5, fatigue: 2.0, subjects: [['physics', 'fluctuating_up']] },
    { offset: 7, minutes: 145, focus: 3.0, fatigue: 4.0, subjects: [['math', 'fatigue_warning'], ['chinese', 'insufficient_data']] },
    { offset: 8, minutes: 80, focus: 4.2, fatigue: 2.5, subjects: [['english', 'efficient_stable']] },
    { offset: 11, minutes: 110, focus: 3.8, fatigue: 3.0, subjects: [['math', 'fluctuating_up'], ['physics', 'insufficient_data']] },
    { offset: 14, minutes: 55, focus: 2.8, fatigue: 4.5, subjects: [['chemistry', 'emotion_blocked']] },
    { offset: 15, minutes: 165, focus: 4.6, fatigue: 2.0, subjects: [['math', 'fatigue_warning'], ['english', 'efficient_stable']] },
  ];

  for (const item of preset) {
    const date = start.add(item.offset, 'day');
    if (date.month() !== start.month()) continue;

    const key = date.format(DATE_FORMAT);
    marks[key] = {
      date: key,
      totalMinutes: item.minutes,
      recordCount: item.subjects.length,
      subjects: item.subjects.map(([subject, stateLabel]) => ({
        subject,
        label: subjectLabels[subject],
        minutes: Math.round(item.minutes / item.subjects.length),
        stateLabel,
      })),
      focusAvg: item.focus,
      fatigueAvg: item.fatigue,
    };
  }

  return { marks, month };
}

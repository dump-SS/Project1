/**
 * 模块③ 学科分配 —— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/stats/subject-distribution` 在 openapi.yaml 中不存在。
 *   实际使用 `GET /api/v1/learning-records`（openapi.yaml 4.2），按 subject 分组累加 durationMinutes。
 * - subject 取值严格取自 openapi.yaml 的 Subject 枚举，中文名与配色统一在 styles/theme.ts。
 */

import { apiGetAllPages } from './http';
import type { LearningRecord, Subject } from '@/types/api';
import type { SubjectPanel, SubjectSlice } from '@/types/view';
import { subjectColors, subjectLabels } from '@/styles/theme';
import { DATE_FORMAT, dayjs, groupRecordsBySubject, sumMinutes } from '@/utils/aggregate';

const DAYS = 30;

function buildSlices(minutesBySubject: Record<string, number>): SubjectPanel {
  const totalMinutes = Object.values(minutesBySubject).reduce((acc, value) => acc + value, 0);

  const slices: SubjectSlice[] = Object.entries(minutesBySubject)
    .filter(([, minutes]) => minutes > 0)
    .map(([subject, minutes]) => ({
      subject: subject as Subject,
      label: subjectLabels[subject as Subject] ?? subject,
      minutes,
      ratio: totalMinutes > 0 ? minutes / totalMinutes : 0,
      color: subjectColors[subject as Subject] ?? subjectColors.other,
    }))
    .sort((a, b) => b.minutes - a.minutes);

  return { slices, totalMinutes };
}

/** 拉取最近 30 天的学科时长占比 */
export async function fetchSubjectDistribution(signal?: AbortSignal): Promise<SubjectPanel> {
  const today = dayjs();
  const records = await apiGetAllPages<LearningRecord>(
    '/learning-records',
    {
      dateFrom: today.subtract(DAYS - 1, 'day').format(DATE_FORMAT),
      dateTo: today.format(DATE_FORMAT),
    },
    signal,
  );

  const bySubject = groupRecordsBySubject(records);
  const minutesBySubject: Record<string, number> = {};
  for (const [subject, subjectRecords] of Object.entries(bySubject)) {
    minutesBySubject[subject] = sumMinutes(subjectRecords);
  }

  return buildSlices(minutesBySubject);
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderSubjectDistribution(): SubjectPanel {
  return buildSlices({
    SX: 620,
    YY: 410,
    WL: 265,
    YW: 180,
    HX: 120,
  });
}

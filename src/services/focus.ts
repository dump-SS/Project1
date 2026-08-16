/**
 * 模块④ 专注程度（日/周/月切换）—— 数据获取。
 *
 * 接口映射说明：
 * - 需求文档里写的 `GET /api/stats/focus?range=` 在 openapi.yaml 中不存在。
 *   实际使用 `GET /api/v1/learning-records`（openapi.yaml 4.2）里的 selfReport.focus，
 *   它在 schema 里就定义为 1-5 的整数（RecordSelfReport.focus，minimum 1 / maximum 5），
 *   与需求中「Y 轴 1-5 分」天然一致，无需换算。
 * - 另有 `GET /api/v1/assessments?subject=`（openapi.yaml 5.2）返回 windowScore，
 *   但它是 0-1 的综合状态分且 subject 为必填、不做跨学科合并（PRD 5.2 明确不做跨学科加权），
 *   不适合本模块「全学科统一专注度曲线」的展示诉求，故未采用。
 * - 时间粒度按需求：日=小时段，周=天，月=周。聚合在前端完成。
 */

import type { Dayjs } from 'dayjs';
import { apiGet, apiGetAllPages } from './http';
import type { LearningRecord, StateLabel, StateResult, StateResultList } from '@/types/api';
import type { FocusPanel, FocusPoint, FocusRange } from '@/types/view';
import { subjectLabels } from '@/styles/theme';
import {
  DATE_FORMAT,
  dayjs,
  groupRecordsByDate,
  round1,
  weekdayLabel,
  weightedFocus,
} from '@/utils/aggregate';

/** 日视图的小时段分桶，覆盖学生的实际作息 */
const HOUR_BUCKETS: Array<{ label: string; startHour: number; endHour: number }> = [
  { label: '06-09', startHour: 6, endHour: 9 },
  { label: '09-12', startHour: 9, endHour: 12 },
  { label: '12-15', startHour: 12, endHour: 15 },
  { label: '15-18', startHour: 15, endHour: 18 },
  { label: '18-21', startHour: 18, endHour: 21 },
  { label: '21-24', startHour: 21, endHour: 24 },
];

const RANGE_DAYS: Record<FocusRange, number> = { day: 1, week: 7, month: 30 };

/**
 * 文艺风评语。
 * 需求要求「AI 生成的文艺风评语」。openapi.yaml 里最接近的是
 *   GET /assessments/current 的 displayText（自然语言、但按学科、且偏客观陈述）
 *   与 GET /recommendations/{id} 的 items[].content（绑定单次学习记录）。
 * 两者都不等价于「整体专注度的一句诗」，故这一句仍按分数段匹配硬编码；
 * 真实的状态说明另行取自 displayText，见 pickStateNote，两者在 UI 上分层展示。
 */
function pickComment(average: number | null): string {
  if (average === null) return '还没有留下痕迹，从今天写第一笔吧 🌱';
  if (average >= 4.5) return '心流渐稳，如溪入海 🌊';
  if (average >= 4) return '专注如灯，照亮前路 ✨';
  if (average >= 3) return '起落之间，节奏自在其中 🍃';
  if (average >= 2) return '有些分神也无妨，慢下来才看得清 🌾';
  return '时光不语，静待花开 🌸';
}

/** 需要优先提示的状态，排在前面的更值得让用户看到 */
const LABEL_PRIORITY: StateLabel[] = [
  'emotion_blocked',
  'fatigue_warning',
  'fluctuating_up',
  'efficient_stable',
];

/**
 * 从各学科的当前状态里挑一条最值得展示的说明。
 * PRD 5.2 规定不做跨学科合并，所以这里是「选一条」而不是「合成一条」，
 * 并在 UI 上标明它属于哪个学科。
 */
function pickStateNote(items: StateResult[]): FocusPanel['stateNote'] {
  const usable = items.filter((item) => item.dataSufficient && item.displayText);
  if (usable.length === 0) return null;

  const ranked = [...usable].sort((a, b) => {
    const rankA = LABEL_PRIORITY.indexOf(a.stateLabel);
    const rankB = LABEL_PRIORITY.indexOf(b.stateLabel);
    if (rankA !== rankB) return (rankA < 0 ? 99 : rankA) - (rankB < 0 ? 99 : rankB);
    return b.recordCount - a.recordCount;
  });

  const top = ranked[0];
  return {
    subject: top.subject,
    subjectLabel: subjectLabels[top.subject] ?? top.subject,
    stateLabel: top.stateLabel,
    text: top.displayText,
  };
}

function buildPanel(
  range: FocusRange,
  points: FocusPoint[],
  records: LearningRecord[],
  stateNote: FocusPanel['stateNote'],
): FocusPanel {
  const overall = weightedFocus(records);
  const average = overall === null ? null : round1(overall);

  return {
    range,
    points,
    average,
    sampleCount: records.length,
    comment: pickComment(average),
    stateNote,
  };
}

/** 日视图：按小时段聚合当天记录 */
function buildDayPoints(records: LearningRecord[]): FocusPoint[] {
  return HOUR_BUCKETS.map((bucket) => {
    const bucketRecords = records.filter((record) => {
      const hour = dayjs(record.startedAt).hour();
      return hour >= bucket.startHour && hour < bucket.endHour;
    });
    const score = weightedFocus(bucketRecords);
    return { label: bucket.label, score: score === null ? null : round1(score) };
  });
}

/** 周视图：按天聚合最近 7 天 */
function buildWeekPoints(records: LearningRecord[], today: Dayjs): FocusPoint[] {
  const byDate = groupRecordsByDate(records);
  return Array.from({ length: 7 }, (_, index) => {
    const date = today.subtract(6 - index, 'day');
    const score = weightedFocus(byDate[date.format(DATE_FORMAT)] ?? []);
    return {
      label: `周${weekdayLabel(date)}`,
      score: score === null ? null : round1(score),
    };
  });
}

/** 月视图：按周聚合最近 30 天，分成 5 个 6 天窗口 */
function buildMonthPoints(records: LearningRecord[], today: Dayjs): FocusPoint[] {
  const buckets = 5;
  const daysPerBucket = 6;

  return Array.from({ length: buckets }, (_, index) => {
    const bucketEnd = today.subtract((buckets - 1 - index) * daysPerBucket, 'day');
    const bucketStart = bucketEnd.subtract(daysPerBucket - 1, 'day');

    const bucketRecords = records.filter((record) => {
      const recordDate = dayjs(record.startedAt);
      return (
        recordDate.isAfter(bucketStart.startOf('day')) &&
        recordDate.isBefore(bucketEnd.endOf('day'))
      );
    });

    const score = weightedFocus(bucketRecords);
    return {
      label: `${bucketStart.format('M/D')}-${bucketEnd.format('M/D')}`,
      score: score === null ? null : round1(score),
    };
  });
}

export async function fetchFocus(range: FocusRange, signal?: AbortSignal): Promise<FocusPanel> {
  const today = dayjs();
  const days = RANGE_DAYS[range];

  const [records, currentStates] = await Promise.all([
    apiGetAllPages<LearningRecord>(
      '/learning-records',
      {
        dateFrom: today.subtract(days - 1, 'day').format(DATE_FORMAT),
        dateTo: today.format(DATE_FORMAT),
      },
      signal,
    ),
    // 状态说明是锦上添花，拿不到不应让整个模块退回占位数据
    apiGet<StateResultList>('/assessments/current', {}, signal).catch(() => null),
  ]);

  const points =
    range === 'day'
      ? buildDayPoints(records)
      : range === 'week'
        ? buildWeekPoints(records, today)
        : buildMonthPoints(records, today);

  return buildPanel(range, points, records, pickStateNote(currentStates?.items ?? []));
}

/**
 * 占位数据。
 * TODO: 仅用于接口联通前把 UI 搭起来，联调通过后此函数即可删除。
 */
export function placeholderFocus(range: FocusRange): FocusPanel {
  const presets: Record<FocusRange, { points: FocusPoint[]; average: number; sampleCount: number }> =
    {
      day: {
        points: [
          { label: '06-09', score: null },
          { label: '09-12', score: 4.2 },
          { label: '12-15', score: 3.1 },
          { label: '15-18', score: 3.8 },
          { label: '18-21', score: 4.5 },
          { label: '21-24', score: 3.4 },
        ],
        average: 3.9,
        sampleCount: 5,
      },
      week: {
        points: [
          { label: '周一', score: 3.6 },
          { label: '周二', score: 4.1 },
          { label: '周三', score: null },
          { label: '周四', score: 3.2 },
          { label: '周五', score: 4.4 },
          { label: '周六', score: 4.0 },
          { label: '周日', score: 4.6 },
        ],
        average: 4.1,
        sampleCount: 12,
      },
      month: {
        points: [
          { label: '7/18-7/23', score: 3.4 },
          { label: '7/24-7/29', score: 3.9 },
          { label: '7/30-8/4', score: 3.7 },
          { label: '8/5-8/10', score: 4.2 },
          { label: '8/11-8/16', score: 4.3 },
        ],
        average: 3.9,
        sampleCount: 41,
      },
    };

  const preset = presets[range];
  return {
    range,
    points: preset.points,
    average: preset.average,
    sampleCount: preset.sampleCount,
    comment: pickComment(preset.average),
    stateNote: {
      subject: 'math',
      subjectLabel: '数学',
      stateLabel: 'fatigue_warning',
      text: '最近几次数学状态有点走低，疲劳感比较明显',
    },
  };
}

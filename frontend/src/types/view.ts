/**
 * 视图模型（View Model）。
 *
 * 这是「接口返回结构」与「组件渲染所需结构」之间的一层。
 * openapi.yaml 只提供原始学习记录，日/周/月的聚合是前端算的，
 * 聚合结果的形状定义在这里，组件不直接消费 API 类型。
 */

import type { GoalOutcome, StateLabel, Subject } from './api';

/** 数据来源：真实接口 / 本地缓存 / 占位数据。用于在 UI 上如实标注，避免缓存或占位数据被误认为实时数据 */
export type DataSource = 'api' | 'cache' | 'placeholder';

export interface PanelState<T> {
  data: T;
  loading: boolean;
  source: DataSource;
  /** 接口失败原因，仅在 source === 'placeholder' 且确实调用过接口时有值 */
  error: string | null;
}

/* ---------- ① 打卡 ---------- */

export interface CheckInDay {
  /** YYYY-MM-DD */
  date: string;
  /** 「一」「二」…「日」 */
  weekdayLabel: string;
  /** 「8/16」 */
  dayLabel: string;
  isToday: boolean;
  checked: boolean;
  totalMinutes: number;
  recordCount: number;
  subjects: Subject[];
  /** 当天一句话总结；接口暂无此能力时为 null */
  summary: string | null;
}

export interface CheckInPanel {
  days: CheckInDay[];
  checkedCount: number;
  totalDays: number;
}

/* ---------- ② 学习时长 ---------- */

export interface DurationPoint {
  date: string;
  dayLabel: string;
  hours: number;
}

export interface DurationPanel {
  todayMinutes: number;
  /** 目标时长；无当日计划时为 null */
  targetMinutes: number | null;
  trend: DurationPoint[];
}

/* ---------- ③ 学科分配 ---------- */

export interface SubjectSlice {
  subject: Subject;
  label: string;
  minutes: number;
  /** 0-1 */
  ratio: number;
  color: string;
}

export interface SubjectPanel {
  slices: SubjectSlice[];
  totalMinutes: number;
}

/* ---------- ④ 专注程度 ---------- */

export type FocusRange = 'day' | 'week' | 'month';

export interface FocusPoint {
  label: string;
  /** 1-5；该时间粒度内无记录时为 null，折线断开而不是画成 0 */
  score: number | null;
}

export interface FocusPanel {
  range: FocusRange;
  points: FocusPoint[];
  /** 1-5；无样本时为 null */
  average: number | null;
  sampleCount: number;
  /** 文艺风评语 */
  comment: string;
  /**
   * 来自 GET /assessments/current 的真实状态说明（displayText）。
   * 按学科返回，这里挑最值得关注的一条；拿不到时为 null，只显示文艺风评语。
   */
  stateNote: {
    subject: Subject;
    subjectLabel: string;
    stateLabel: StateLabel;
    text: string;
  } | null;
}

/* ---------- ⑤ 日历 ---------- */

export interface CalendarSubjectStat {
  subject: Subject;
  label: string;
  minutes: number;
  /** 当日该学科的状态标签，来自 GET /assessments；拿不到时为 null */
  stateLabel: StateLabel | null;
}

/**
 * 日历详情。
 *
 * `records` 字段是新增的：原来只有聚合后的总时长/学科/标签。
 * 用户从日历里直接看到并删除单条记录是 PRD 5.2 边界场景「记录删除回溯」，
 * 因此 DayDetailPanel 渲染时需要有原始 LearningRecord 列表。
 */
export interface CalendarDayDetail {
  date: string;
  totalMinutes: number;
  recordCount: number;
  subjects: CalendarSubjectStat[];
  /** 当天平均专注度 1-5 */
  focusAvg: number | null;
  /** 当天平均疲劳度 1-5 */
  fatigueAvg: number | null;
  /** 当日学习记录的原始列表，供「按记录删除」使用；占位数据下不填 */
  records?: import('./api').LearningRecord[];
}

export interface CalendarPanel {
  /** key 为 YYYY-MM-DD */
  marks: Record<string, CalendarDayDetail>;
  month: string;
}

/* ---------- ⑥ 目标 ---------- */

export interface GoalCard {
  goalId: string;
  title: string;
  type: 'short_term' | 'long_term';
  typeLabel: string;
  subject: Subject;
  subjectLabel: string;
  targetDate: string | null;
  status: 'active' | 'archived';
  /** 归档终态；契约补齐前恒为 null，此时 archived 一律显示为「已完成」 */
  outcome: GoalOutcome | null;
  statusLabel: string;
  /** 0-100 */
  percent: number;
  plannedTasks: number;
  completedTasks: number;
  /** 完成总结；接口暂无此字段时为 null */
  completionNote: string | null;
}

export interface GoalPanel {
  active: GoalCard[];
  finished: GoalCard[];
}

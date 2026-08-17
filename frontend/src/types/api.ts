/**
 * API 类型定义。
 *
 * 严格对应 docs/openapi.yaml 的 components.schemas，字段名、可空性、枚举取值均以该文件为准。
 * 新增字段前请先改 openapi.yaml —— 它是前后端与 QA 的唯一契约来源。
 */

/* ---------- 枚举字典（openapi.yaml 0.4 节） ---------- */

export type Subject =
  | 'chinese'
  | 'math'
  | 'english'
  | 'physics'
  | 'chemistry'
  | 'biology'
  | 'history'
  | 'geography'
  | 'politics'
  | 'other';

export type Stage = 'junior' | 'senior';

export type GoalType = 'short_term' | 'long_term';

export type TaskStatus = 'pending' | 'completed' | 'partial' | 'abandoned';

export type Completion = 'completed' | 'partial' | 'abandoned';

export type Emotion = 'positive' | 'neutral' | 'negative';

export type DifficultyFeel = 'easy' | 'moderate' | 'hard';

export type Trend = 'up' | 'flat' | 'down';

export type StateLabel =
  | 'efficient_stable'
  | 'fatigue_warning'
  | 'emotion_blocked'
  | 'fluctuating_up'
  | 'insufficient_data';

export type RecScene = 'post_session' | 'weekly_review';

export type GenerationSource = 'llm' | 'template';

export type Rating = 'useful' | 'neutral' | 'not_useful';

/* ---------- 通用结构 ---------- */

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    /** 校验失败的字段路径，仅参数校验错误时出现 */
    field?: string;
  };
}

export interface Pagination {
  page: number;
  pageSize: number;
  total: number;
}

export interface GenerationStatus {
  status: 'pending' | 'ready' | 'insufficient_data' | 'failed';
  source?: GenerationSource;
  completedAt?: string;
}

/* ---------- 用户与设置 ---------- */

export interface Settings {
  aiWeightTuningEnabled: boolean;
  sendTextToAI: boolean;
  updatedAt: string;
}

export interface SettingsUpdate {
  aiWeightTuningEnabled?: boolean;
  sendTextToAI?: boolean;
}

/* ---------- 学习记录 ---------- */

export interface RecordBehavior {
  completion: Completion;
  /** 正确率 0-1；无客观测验时后端不返回 */
  accuracy?: number;
  interruptions?: number;
  /** 页面失焦次数，小程序弱信号 */
  blurCount?: number;
}

export interface RecordSelfReport {
  /** 专注度 1-5 */
  focus: number;
  /** 疲劳度 1-5 */
  fatigue: number;
  emotion: Emotion;
  difficultyFeel: DifficultyFeel;
}

export interface LearningRecord {
  recordId: string;
  subject: Subject;
  startedAt: string;
  durationMinutes: number;
  /** 自由学习时为 null */
  planTaskId: string | null;
  behavior: RecordBehavior;
  selfReport: RecordSelfReport;
  createdAt: string;
}

export interface LearningRecordList {
  items: LearningRecord[];
  pagination: Pagination;
}

export interface RecordInput {
  subject: Subject;
  startedAt: string;
  durationMinutes: number;
  planTaskId?: string;
  behavior: RecordBehavior;
  selfReport: RecordSelfReport;
  note?: string;
  skipRecommendation?: boolean;
}

export interface AssessmentSnapshot {
  assessmentId: string;
  subject: Subject;
  windowScore: number;
  trend: Trend;
  stateLabel: StateLabel;
  dataSufficient: boolean;
  recordCount: number;
}

export interface LearningRecordCreated extends LearningRecord {
  assessment: AssessmentSnapshot;
  recommendation: {
    recommendationId: string;
    status: string;
  } | null;
}

/* ---------- 个性化建议 ---------- */

export interface RecommendationItem {
  title: string;
  content: string;
}

export interface RecommendationBasedOn {
  assessmentId?: string;
  recordId?: string;
  stateLabel: StateLabel;
  explain: string;
}

export interface FeedbackRecord {
  rating: Rating;
  reason?: string | null;
  submittedAt: string;
}

export interface Recommendation {
  recommendationId: string;
  scene: RecScene;
  subject?: Subject | null;
  generation: GenerationStatus;
  items?: RecommendationItem[] | null;
  basedOn?: RecommendationBasedOn;
  feedback?: FeedbackRecord | null;
}

/* ---------- 学习计划 ---------- */

export interface PlanTask {
  taskId: string;
  subject: Subject;
  topic: string;
  estimatedMinutes: number;
  priority: number;
  status: TaskStatus;
  goalId: string | null;
}

export interface PlanAdaptation {
  assessmentId: string;
  stateLabel: StateLabel;
  adjustment: string;
  note: string;
}

export interface Plan {
  planId: string;
  planDate: string;
  availableMinutes: number;
  /** 新用户无历史数据时为 null */
  adaptedFrom: PlanAdaptation | null;
  tasks: PlanTask[];
  createdAt: string;
}

export interface PlanList {
  items: Plan[];
  pagination: Pagination;
}

/* ---------- 学习目标 ---------- */

export interface GoalProgress {
  plannedTasks: number;
  completedTasks: number;
  ratio: number;
}

/**
 * 注意：接口只有 active / archived 两种状态，没有 completed / abandoned。
 * 归档代替删除（openapi.yaml 2.3），UI 上的「已完成」语义由 archived 承担。
 */
export type GoalStatus = 'active' | 'archived';

/**
 * 归档终态。**契约中尚不存在此字段**，已提给后端作为纯增量改动。
 * 这里预先声明为可选，后端上线后前端无需改动即可自动生效；
 * 在此之前所有 archived 目标统一按「已完成」展示。
 */
export type GoalOutcome = 'achieved' | 'abandoned' | 'expired';

export interface GoalSummary {
  goalId: string;
  type: GoalType;
  subject: Subject;
  title: string;
  targetDate: string | null;
  status: GoalStatus;
  progress: GoalProgress;
  /** 契约待补充，见 GoalOutcome 说明 */
  outcome?: GoalOutcome | null;
  /** 契约待补充：目标完成总结 */
  completionNote?: string | null;
}

export interface Goal extends GoalSummary {
  description: string | null;
  createdAt: string;
}

export interface GoalList {
  items: GoalSummary[];
  pagination: Pagination;
}

/* ---------- 状态评估 ---------- */

export interface StateBasedOn {
  recordIds: string[];
  signals: string[];
}

export interface StateResult {
  /** 数据不足时为 null */
  assessmentId: string | null;
  subject: Subject;
  /** 数据不足时后端不返回 */
  windowScore?: number;
  trend?: Trend;
  stateLabel: StateLabel;
  /** 面向用户的自然语言说明 */
  displayText: string;
  dataSufficient: boolean;
  recordCount: number;
  windowSize: number;
  basedOn?: StateBasedOn;
  computedAt?: string;
}

export interface StateResultList {
  items: StateResult[];
}

export interface AssessmentHistoryPoint {
  date: string;
  windowScore: number;
  stateLabel: StateLabel;
  trend: Trend;
}

export interface AssessmentHistory {
  subject: Subject;
  items: AssessmentHistoryPoint[];
}

/* ---------- 学习总结与复盘 ---------- */

export interface SummaryContent {
  overview: string;
  patterns: string[];
  suggestions: string[];
  encouragement: string;
}

export interface SummaryDataPoints {
  recordCount?: number;
  subjects?: Subject[];
  planCompletionRatio?: number;
  referencedAssessmentIds?: string[];
  minRequired?: number;
}

export interface Summary {
  summaryId: string;
  periodStart?: string;
  periodEnd?: string;
  generation: GenerationStatus;
  /** 数据不足或生成失败时为 null */
  content: SummaryContent | null;
  dataPoints?: SummaryDataPoints;
  message?: string;
}

export interface SummaryList {
  items: Summary[];
  pagination: Pagination;
}

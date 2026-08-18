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

/**
 * 删除学习记录后的响应（openapi.yaml LearningRecordDeleted）。
 * 字段含义见 AssessmentSnapshot。
 */
export interface LearningRecordDeleted {
  deleted: boolean;
  recordId: string;
  recalculatedAssessment: AssessmentSnapshot;
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

export interface RecommendationFeedbackResult {
  recommendationId: string;
  feedback: FeedbackRecord;
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

/**
 * 创建目标请求体（openapi.yaml GoalCreate）。
 * 至少传 type + subject + title；description / targetDate / templateId 可选。
 * 字段长度与契约一致：title ≤ 50 字、description ≤ 200 字。
 */
export interface GoalCreate {
  type: GoalType;
  subject: Subject;
  title: string;
  description?: string;
  targetDate?: string;
  templateId?: string;
}

/**
 * 更新目标请求体（openapi.yaml GoalUpdate）。字段全可选，但至少传一项。
 * 归档通过 `status: 'archived'` 表达——契约里没有独立 DELETE，归档即"软删除"。
 */
export interface GoalUpdate {
  title?: string;
  description?: string;
  targetDate?: string;
  status?: GoalStatus;
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
  /** 复盘生成时记录的「今日已完成 N / M」快照（PRD 5.4）。
   *  注意：这是 summary 生成时的瞬时值，不是当前实时数。 */
  planCompletedCount?: number;
  planTotalCount?: number;
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
  /** 用户已提交的反馈，未提交时为 null */
  feedback?: FeedbackRecord | null;
}

export interface SummaryList {
  items: Summary[];
  pagination: Pagination;
}

/** 已提交的反馈记录（openapi.yaml FeedbackRecord） */
export interface FeedbackRecord {
  rating: Rating;
  /** 用户补充说明，可为空 */
  reason?: string | null;
  submittedAt: string;
}

/** 手动触发复盘后的受理响应（openapi.yaml SummaryPending） */
export interface SummaryPending {
  summaryId: string;
  periodStart: string;
  periodEnd: string;
  generation: GenerationStatus;
  createdAt: string;
}

/** 复盘反馈提交结果（openapi.yaml SummaryFeedbackResult） */
export interface SummaryFeedbackResult {
  summaryId: string;
  feedback: FeedbackRecord;
}

/* ---------- 用户与设置（openapi.yaml 0.5 节） ---------- */

/** 监护人授权状态 */
export type GuardianAuthorizationStatus = 'pending' | 'active' | 'revoked' | 'expired';

export interface GuardianAuthorization {
  status: GuardianAuthorizationStatus;
  /** 授权到期时间，active 时出现 */
  expiresAt?: string;
}

/** 当前用户资料（openapi.yaml User） */
export interface User {
  userId: string;
  stage: Stage;
  grade: string;
  subjects: Subject[];
  guardianAuthorization: GuardianAuthorization;
  /** 是否已完成建档引导 */
  onboardingCompleted: boolean;
}

/** 幂等建档请求体，字段全必填（openapi.yaml UserProfilePut） */
export interface UserProfilePut {
  stage: Stage;
  grade: string;
  subjects: Subject[];
}

/** 局部更新请求体，字段全可选（openapi.yaml UserProfilePatch） */
export interface UserProfilePatch {
  stage?: Stage;
  grade?: string;
  subjects?: Subject[];
}

/** 监护人授权请求体：邮箱/手机号二选一必填（openapi.yaml GuardianAuthorizationRequest） */
export interface GuardianAuthorizationRequest {
  guardianEmail?: string;
  guardianPhone?: string;
}

/* ---------- 个性化建议（openapi.yaml 6.x） ---------- */

/** 手动请求建议后的受理响应 */
export interface RecommendationPending {
  recommendationId: string;
  scene: RecScene;
  subject?: Subject | null;
  generation: GenerationStatus;
  createdAt: string;
}

/** 手动请求生成建议请求体（scene 必填；post_session 场景建议必传 subject） */
export interface RecommendationCreate {
  scene: RecScene;
  subject?: Subject;
  recordId?: string;
}

export interface RecommendationList {
  items: Recommendation[];
  pagination: Pagination;
}

/** 建议反馈提交结果 */
export interface RecommendationFeedbackResult {
  recommendationId: string;
  feedback: FeedbackRecord;
}

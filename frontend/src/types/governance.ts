/**
 * G 板块（pilot 运营与治理）类型 —— 对应 openapi.yaml v1.7.0 的 governance 相关 schema。
 *
 * ⚠️ 本文件由 G 板块维护。`types/api.ts` 是 X0/X1 共管文件（G 不动手），
 * X1 收口时可将这里的定义折入 api.ts 并删除本文件（字段以契约为准，勿改名）。
 */

/** 功能档位（D38）：chat=对话式 / embedded=嵌入式 / advanced=高级 / multimodal=文件解析 */
export type UsageFeatureTier = 'chat' | 'embedded' | 'advanced' | 'multimodal';

/** 推理等级（#33） */
export type ReasoningTier = 'quick' | 'standard' | 'deep';

/** 违规处置动作（#43：1 警告 → 3 临时封 → 永久） */
export type ViolationAction = 'warn' | 'temp_ban' | 'perm_ban';

/** 奖章里程碑（#49 最小版，禁止扩展成积分/商城/排行） */
export type MedalMilestone =
  | 'first_record'
  | 'streak_7_days'
  | 'first_summary'
  | 'first_goal_achieved'
  | 'first_topic_book';

/** 埋点三块（D39） */
export type AnalyticsCategory = 'chat_interaction' | 'ai_quality' | 'profile_trace';

/** 按用户记录的模型数值成本（只存数值，不含任何提示词/输出内容；#9/D38） */
export interface UsageLedgerEntry {
  id: string;
  featureTier: UsageFeatureTier;
  reasoningTier: ReasoningTier | null;
  model: string;
  tokensIn: number;
  tokensOut: number;
  /** 数值成本（内部计价，非对用户计费） */
  cost: number;
  createdAt: string;
}

/** GET /me/usage 响应 */
export interface UsageLedgerList {
  items: UsageLedgerEntry[];
  totalCost?: number;
  totalTokensIn?: number;
  totalTokensOut?: number;
}

/** 违规处置留痕（#43，本人可查） */
export interface ViolationLog {
  id: string;
  level: number;
  action: ViolationAction;
  reason: string;
  createdAt: string;
}

/** GET /me/violations 响应 */
export interface ViolationLogList {
  items: ViolationLog[];
}

/** 奖章（#49） */
export interface Medal {
  medalId: string;
  milestone: MedalMilestone;
  awardedAt: string;
}

/** GET /me/medals 响应 */
export interface MedalList {
  items: Medal[];
}

/** POST /error-reports 请求体（#46） */
export interface ErrorReportCreate {
  /** 消息级报错时的消息 ID；设置常驻入口不传 */
  messageId?: string;
  /** 该条消息的意图判定结果（便于定位问题） */
  intent?: string;
  description: string;
  /** 上下文快照（消息角色/结构化体等，不含对话原文流水） */
  context?: Record<string, unknown>;
}

/** POST /error-reports 响应 */
export interface ErrorReport {
  id: string;
  messageId: string | null;
  intent: string | null;
  description: string;
  context: Record<string, unknown> | null;
  createdAt: string;
}

/** POST /analytics/events 请求体（D39） */
export interface AnalyticsEventCreate {
  category: AnalyticsCategory;
  eventType: string;
  sessionId?: string;
  payload?: Record<string, unknown>;
  occurredAt?: string;
}

/** POST /analytics/events 响应（返回脱敏后实际落库内容） */
export interface AnalyticsEvent {
  id: string;
  category: AnalyticsCategory;
  eventType: string;
  sessionId: string | null;
  payload: Record<string, unknown> | null;
  occurredAt: string;
  createdAt: string;
}

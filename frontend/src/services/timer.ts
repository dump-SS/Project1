/**
 * 专注计时（服务端会话）—— D30 / D31 / D32 / #14。
 *
 * 接口映射（docs/openapi.yaml v1.7.1）：
 * - POST   /timer-sessions                       开始计时（已有进行中会话时 409）
 * - GET    /timer-sessions/current               当前会话 + 恢复视图（active=false 是正常流程）
 * - GET    /timer-sessions/{sessionId}           会话详情
 * - POST   /timer-sessions/{sessionId}/heartbeat 上报心跳（僵尸判定的唯一依据）
 * - POST   /timer-sessions/{sessionId}/segments  切换任务（开新的一段，#14）
 * - POST   /timer-sessions/{sessionId}/finish    结束并收尾（原子落学习记录）
 * - DELETE /timer-sessions/{sessionId}           丢弃（裁决卡「丢弃」，不产生记录）
 *
 * **为什么计时状态在服务端**：原来 `/study-timer` 的上下文靠 react-router 的
 * `navigate(state)` 传参，刷新或直链进来就丢任务、丢时长、丢 planId。
 * 目标态 §3.6 定的口径是「服务端持久化进行中的计时会话，前端仅是视图」——
 * 所以本模块是"专注态的唯一真相源"，前端回来只需 `getCurrentTimerSession()` 按 mode 恢复。
 *
 * ⚠️ 类型定义放在本文件而**不是** `types/api.ts`：后者按板块契约归 X1 管
 * （X0 定字段 / X1 管导出），C 板块不动手。等 X1 收口时把这里的定义合并过去即可。
 */

import { apiDelete, apiGet, apiPost } from './http';
import type { Subject } from '@/types/api';

/** openapi.yaml TimerMode */
export type TimerMode = 'countdown' | 'countup';
/** openapi.yaml TimerStatus */
export type TimerStatus = 'running' | 'finished' | 'abandoned';
/** openapi.yaml Completion */
export type Completion = 'completed' | 'partial' | 'abandoned';
/** openapi.yaml Emotion */
export type Emotion = 'positive' | 'neutral' | 'negative';
/** openapi.yaml DifficultyFeel */
export type DifficultyFeel = 'easy' | 'moderate' | 'hard';

/**
 * 自评（openapi.yaml RecordSelfReport v1.7.1）。
 *
 * ⚠️ 四字段**全部可空**：三层收尾里唯一"半强制"的只有完成度；专注/疲劳/难度是
 * 模型从"一句感受"转译的软字段，情绪快捷词也只是"可选兜底"。转译不出就留空——
 * 服务端会跳过该项并按可用部分归一化，**不造数**（D34）。
 */
export interface SelfReportInput {
  focus?: number | null;
  fatigue?: number | null;
  emotion?: Emotion | null;
  difficultyFeel?: DifficultyFeel | null;
}

export interface TimerSegment {
  segmentId: string;
  taskId?: string | null;
  startedAt: string;
  endedAt?: string | null;
  seconds?: number | null;
}

export interface TimerSession {
  sessionId: string;
  mode: TimerMode;
  startedAt: string;
  targetMinutes?: number | null;
  planId?: string | null;
  taskId?: string | null;
  subject: Subject;
  status: TimerStatus;
  endedAt?: string | null;
  /** 有效时长（秒）—— ≠ 墙上时长；倒计时封顶 target */
  effectiveSeconds?: number | null;
  lastHeartbeatAt?: string | null;
  segments: TimerSegment[];
  createdAt: string;
}

/**
 * 恢复视图（D30 按 mode 分支计算）。
 * `needsVerdict=true` 表示识别到**异常会话**，必须弹**恢复裁决卡**（D31），**不得自动记账**。
 */
export interface TimerRestore {
  sessionId: string;
  mode: TimerMode;
  /** 仅 countdown：剩余 = target − 已过；≤0 视为已到点（软提醒，不自动结束） */
  remainingSeconds?: number | null;
  /** 仅 countup：累计 = now − startedAt */
  elapsedSeconds?: number | null;
  needsVerdict: boolean;
  /** 裁决卡「保留按 X 记」的预填值 */
  suggestedMinutes?: number | null;
}

export interface TimerCurrent {
  active: boolean;
  session?: TimerSession | null;
  restore?: TimerRestore | null;
}

export interface TimerSessionStart {
  mode: TimerMode;
  /** 仅 countdown 需要；countup 传了会被忽略（不报错） */
  targetMinutes?: number;
  planId?: string;
  taskId?: string;
  subject?: Subject;
}

export interface TimerFinishInput {
  completion: Completion;
  selfReport?: SelfReportInput;
  /**
   * 显式传入时**覆盖**服务端按 mode 算出的有效时长。
   * 前端只在"有过暂停"时传（服务端不知道前端暂停了多久）；
   * 无暂停时留空，让服务端按 mode 算——倒计时的封顶逻辑在服务端更可靠。
   */
  durationMinutes?: number;
  note?: string;
  skipRecommendation?: boolean;
}

/** 提交记录后返回的建议句柄（轮询 GET /recommendations/{id} 用） */
export interface RecommendationHandle {
  recommendationId: string;
  status: string;
}

/** finish 的响应与 POST /learning-records 同构 */
export interface LearningRecordCreated {
  recordId: string;
  subject: Subject;
  startedAt: string;
  durationMinutes: number;
  planTaskId?: string | null;
  behavior: {
    completion: Completion;
    accuracy?: number | null;
    interruptions?: number;
    blurCount?: number | null;
  };
  selfReport?: SelfReportInput | null;
  note?: string | null;
  source: 'self_report' | 'exam';
  sourceExamId?: string | null;
  assessment: {
    assessmentId?: string | null;
    subject: Subject;
    windowScore?: number | null;
    trend?: string | null;
    stateLabel: string;
    dataSufficient: boolean;
    recordCount: number;
  };
  recommendation?: RecommendationHandle | null;
  createdAt: string;
}

/** 开始计时。已有进行中会话时后端返回 409（不静默接管、也不静默丢弃）。 */
export function startTimerSession(body: TimerSessionStart): Promise<TimerSession> {
  return apiPost<TimerSession>('/timer-sessions', body);
}

/** 当前会话 + 恢复视图。进页面 / 刷新 / 换设备回来都调它。 */
export function getCurrentTimerSession(signal?: AbortSignal): Promise<TimerCurrent> {
  return apiGet<TimerCurrent>('/timer-sessions/current', undefined, signal);
}

export function getTimerSession(sessionId: string, signal?: AbortSignal): Promise<TimerSession> {
  return apiGet<TimerSession>(`/timer-sessions/${sessionId}`, undefined, signal);
}

/**
 * 上报心跳。**僵尸判定与「异常会话」识别的唯一依据**：
 * 不刷新心跳的后果不是报错，而是下次回来会被判成异常会话、要求用户裁决，所以宁可多报。
 * 前端应定时上报，并在每次用户交互时顺带上报。
 */
export function heartbeatTimerSession(sessionId: string): Promise<TimerSession> {
  return apiPost<TimerSession>(`/timer-sessions/${sessionId}/heartbeat`);
}

/** 切换任务 → 开新的一段（#14：一会话内分段，不允许并行计时）。 */
export function switchTimerTask(sessionId: string, taskId?: string | null): Promise<TimerSegment> {
  return apiPost<TimerSegment>(`/timer-sessions/${sessionId}/segments`, { taskId: taskId ?? null });
}

/**
 * 结束并收尾 —— 会话结束与落学习记录是**一个原子请求**。
 * 不在前端分两步（先结束、再 POST /learning-records）：两步之间失败会留下
 * "会话结束了但没有记录"的黑洞，正是 D31 要消灭的僵尸形态。
 */
export function finishTimerSession(
  sessionId: string,
  body: TimerFinishInput,
): Promise<LearningRecordCreated> {
  return apiPost<LearningRecordCreated>(`/timer-sessions/${sessionId}/finish`, body);
}

/** 裁决卡「丢弃」：会话标记为 abandoned，**不产生任何学习记录**。 */
export function discardTimerSession(
  sessionId: string,
): Promise<{ discarded: boolean; sessionId: string }> {
  return apiDelete<{ discarded: boolean; sessionId: string }>(`/timer-sessions/${sessionId}`);
}

// ---------- 纯函数：恢复与展示（不碰网络，便于单测与复用） ----------

/**
 * 按 mode 计算当前已过秒数。
 *
 * 服务端只给"会话起点 + 模式"，**不持续下发剩余时间**——所以前端每秒自己按
 * `startedAt` 推算，而不是维护一个递减的本地计数器。这是"刷新不丢上下文"的关键：
 * 本地计数器一刷新就归零，而按起点推算永远是对的。
 */
export function computeElapsedSeconds(
  session: Pick<TimerSession, 'startedAt'>,
  nowMs: number,
  pausedSeconds = 0,
): number {
  const startedMs = new Date(session.startedAt).getTime();
  if (Number.isNaN(startedMs)) return 0;
  const wallSeconds = (nowMs - startedMs) / 1000;
  return Math.max(0, Math.floor(wallSeconds - pausedSeconds));
}

/** 展示用：剩余（倒计时）或累计（正计时）。倒计时到点后返回 0，不显示负数。 */
export function computeDisplaySeconds(
  session: Pick<TimerSession, 'mode' | 'startedAt' | 'targetMinutes'>,
  nowMs: number,
  pausedSeconds = 0,
): { remaining: number | null; elapsed: number } {
  const elapsed = computeElapsedSeconds(session, nowMs, pausedSeconds);
  if (session.mode === 'countdown') {
    const target = (session.targetMinutes ?? 0) * 60;
    return { remaining: Math.max(0, target - elapsed), elapsed };
  }
  return { remaining: null, elapsed };
}

/** 倒计时是否已到点（到点是**软提醒**，不自动结束，D32）。 */
export function isCountdownReached(
  session: Pick<TimerSession, 'mode' | 'targetMinutes'>,
  elapsedSeconds: number,
): boolean {
  if (session.mode !== 'countdown') return false;
  return elapsedSeconds >= (session.targetMinutes ?? 0) * 60;
}

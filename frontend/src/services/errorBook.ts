/**
 * 板块二 · 题本服务（v2.1 转正；D48 升格为「题本」）
 *
 * 对接真实后端 /api/v1/error-book/*（docs/openapi.yaml 错题本段）。
 * 原文 rawText/studentAnswer/correctAnswer/errorNote 只在本地，永不出域。
 *
 * D48：错因（errorCause）与意图（intent）是**两个正交维度**——
 * 有错因 = 错题，只有意图 = star 题；两者都进复习队列，但 mastery 只消费有错因的。
 * 返考措辞统一叫「复习 / 小测」，不叫「组卷」。
 */

import { apiDelete, apiGet, apiPatch, apiPost } from './http';

/** 结构化错因（契约 ErrorCause，取值不得另造） */
export type ErrorCause =
  | 'concept_unclear'
  | 'calculation_error'
  | 'misreading'
  | 'careless'
  | 'knowledge_gap'
  | 'other';

/** 主观意图（契约 ErrorIntent） */
export type ErrorIntent = 'review' | 'good' | 'typical' | 'doubtful';

export const ERROR_CAUSE_LABEL: Record<ErrorCause, string> = {
  concept_unclear: '概念不清',
  calculation_error: '计算失误',
  misreading: '审题偏差',
  careless: '粗心',
  knowledge_gap: '知识漏洞',
  other: '其他',
};

export const ERROR_INTENT_LABEL: Record<ErrorIntent, string> = {
  review: '想复习',
  good: '好题',
  typical: '典型题',
  doubtful: '存疑',
};

export interface LinkedPoint {
  pointId: string;
  name?: string | null;
  confidence?: number | null;
}

export interface ErrorRecord {
  errorId: string;
  subject: string;
  rawText: string;
  studentAnswer?: string | null;
  correctAnswer?: string | null;
  errorType?: string | null;
  errorNote?: string | null;
  status: 'open' | 'resolved';
  points: LinkedPoint[];
  createdAt: string;
  lastReviewedAt?: string | null;
  /** D48 结构化错因；null = 非错题（star 题） */
  errorCause?: ErrorCause | null;
  /** D48 主观意图 */
  intent?: ErrorIntent | null;
  /** D49 来源考试 */
  sourceExamId?: string | null;
}

export interface ErrorRecordCreate {
  subject: string;
  rawText: string;
  studentAnswer?: string;
  correctAnswer?: string;
  errorType?: string;
  errorNote?: string;
  pointIds?: string[];
  errorCause?: ErrorCause;
  intent?: ErrorIntent;
  sourceExamId?: string;
}

export interface ErrorRecordUpdate {
  errorType?: string;
  errorNote?: string;
  status?: 'open' | 'resolved';
  pointIds?: string[];
  errorCause?: ErrorCause;
  intent?: ErrorIntent;
  /** 传 null 表示清除来源考试关联 */
  sourceExamId?: string | null;
}

export interface ReviewResult {
  correct: boolean;
  nextReviewAt: string;
  intervalDays: number;
}

/** GET /error-book 列表 */
export function fetchErrorBook(params: {
  subject?: string;
  status?: string;
  /** D48 按错因筛选 */
  errorCause?: ErrorCause;
  /** D48 按意图筛选（与错因正交，组合为「且」） */
  intent?: ErrorIntent;
  page?: number;
  pageSize?: number;
}): Promise<{ items: ErrorRecord[]; pagination: { page: number; pageSize: number; total: number } }> {
  return apiGet('/error-book', params as Record<string, string | number | undefined>);
}

/** POST /error-book 录入 */
export function createErrorRecord(payload: ErrorRecordCreate): Promise<ErrorRecord> {
  return apiPost('/error-book', payload);
}

/** GET /error-book/{id} 详情 */
export function fetchErrorRecord(errorId: string): Promise<ErrorRecord> {
  return apiGet(`/error-book/${errorId}`);
}

/** PATCH /error-book/{id} 更新 */
export function updateErrorRecord(errorId: string, payload: ErrorRecordUpdate): Promise<ErrorRecord> {
  return apiPatch(`/error-book/${errorId}`, payload);
}

/** DELETE /error-book/{id} 软删 */
export function deleteErrorRecord(errorId: string): Promise<{ deleted: boolean; errorId: string }> {
  return apiDelete(`/error-book/${errorId}`);
}

/** POST /error-book/{id}/review 复习 */
export function reviewErrorRecord(errorId: string, recallCorrect: boolean): Promise<ReviewResult> {
  return apiPost(`/error-book/${errorId}/review`, { recallCorrect });
}

/**
 * 板块二 · 错题本服务（v2.1 转正）
 *
 * 对接真实后端 /api/v1/error-book/*（docs/openapi.yaml v1.5 错题本段）。
 * 原文 rawText/studentAnswer/correctAnswer/errorNote 只在本地，永不出域。
 */

import { apiDelete, apiGet, apiPatch, apiPost } from './http';

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
}

export interface ErrorRecordCreate {
  subject: string;
  rawText: string;
  studentAnswer?: string;
  correctAnswer?: string;
  errorType?: string;
  errorNote?: string;
  pointIds?: string[];
}

export interface ErrorRecordUpdate {
  errorType?: string;
  errorNote?: string;
  status?: 'open' | 'resolved';
  pointIds?: string[];
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

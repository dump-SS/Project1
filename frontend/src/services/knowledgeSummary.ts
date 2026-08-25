/**
 * 学科知识复盘（板块二 v2.2 / S0-T4）
 *
 * 接口：POST /knowledge-summary（同步返回 summary；后端落 summaries.dimension=knowledge）。
 * 429 = 今日次数上限；其余错误按降级提示。
 */
import { apiPost, ApiError } from './http';

export interface KnowledgeSummaryResult {
  summary: string;
}

export function createKnowledgeSummary(subject: string, period: string): Promise<KnowledgeSummaryResult> {
  return apiPost<KnowledgeSummaryResult>('/knowledge-summary', { subject, period });
}

/** 提取 429 限流错误（供 UI 显示「今日已达上限」） */
export function isRateLimited(err: unknown): boolean {
  return err instanceof ApiError && err.status === 429;
}

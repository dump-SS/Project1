/**
 * 学习总结与复盘（PRD 5.4）—— 数据获取。
 *
 * 接口映射（openapi.yaml 7.x）：
 * - POST /summaries                      手动触发生成复盘（返回 202 SummaryPending）
 * - GET  /summaries/{summaryId}          复盘详情（ready / insufficient_data / failed）
 * - PUT  /summaries/{summaryId}/feedback 提交「准不准/有没有用」轻量反馈
 *
 * 生成是异步的：POST 只受理（status=pending），需要前端轮询 GET 详情，
 * 直到 generation.status 进入终态（ready / insufficient_data / failed）。
 */

import { apiGet, apiPost, apiPut } from './http';
import type { Rating, Summary, SummaryFeedbackResult, SummaryPending } from '@/types/api';

/** 手动触发指定时间段的复盘生成。periodStart/periodEnd 为 YYYY-MM-DD。 */
export function createSummary(periodStart: string, periodEnd: string): Promise<SummaryPending> {
  return apiPost<SummaryPending>('/summaries', { periodStart, periodEnd });
}

/** 拉取复盘详情；生成未完成时 generation.status 仍为 pending。 */
export function getSummary(summaryId: string, signal?: AbortSignal): Promise<Summary> {
  return apiGet<Summary>(`/summaries/${summaryId}`, undefined, signal);
}

/** 提交复盘反馈（rating 必填，reason 可选 ≤100 字）。 */
export function submitSummaryFeedback(
  summaryId: string,
  rating: Rating,
  reason?: string,
): Promise<SummaryFeedbackResult> {
  return apiPut<SummaryFeedbackResult>(`/summaries/${summaryId}/feedback`, {
    rating,
    reason: reason?.trim() ? reason.trim() : null,
  });
}

/** 复盘生成是否已到终态（生成完成 / 数据不足 / 生成失败）。 */
export function isSummaryTerminal(status: string | undefined): boolean {
  return status === 'ready' || status === 'insufficient_data' || status === 'failed';
}

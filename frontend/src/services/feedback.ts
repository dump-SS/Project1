/**
 * AI 质量反馈与用户报错 —— 数据提交。
 *
 * 接口映射（docs/openapi.yaml）：
 * - PUT /recommendations/{recommendationId}/feedback  建议反馈（rating: useful/neutral/not_useful）
 * - PUT /summaries/{summaryId}/feedback               复盘反馈（同 RatingFeedback）
 * - POST /error-reports                               用户报错（#46：设置常驻 + 消息级按钮两处入口）
 * - POST /analytics/events                            埋点上报（D39：chat_interaction/ai_quality/profile_trace）
 *
 * 建议与复盘反馈语义一致：一条建议/复盘至多一份反馈，用户改主意即覆盖（PUT 幂等）。
 */

import { apiPost, apiPut } from './http';
import type {
  Rating,
  RecommendationFeedbackResult,
  SummaryFeedbackResult,
} from '@/types/api';
import type { AnalyticsEvent, AnalyticsEventCreate, ErrorReport, ErrorReportCreate } from '@/types/governance';

export function putRecommendationFeedback(
  recommendationId: string,
  rating: Rating,
): Promise<RecommendationFeedbackResult> {
  return apiPut<RecommendationFeedbackResult>(
    `/recommendations/${recommendationId}/feedback`,
    { rating },
  );
}

export function putSummaryFeedback(
  summaryId: string,
  rating: Rating,
): Promise<SummaryFeedbackResult> {
  return apiPut<SummaryFeedbackResult>(`/summaries/${summaryId}/feedback`, { rating });
}

/**
 * 提交用户报错（#46）。设置常驻入口不传 messageId；消息级按钮带 messageId + intent + 上下文
 * （context 只放结构化信息，不含对话原文流水——与 D45 原文留存口径分开）。
 */
export function postErrorReport(payload: ErrorReportCreate): Promise<ErrorReport> {
  return apiPost<ErrorReport>('/error-reports', payload);
}

/** 上报结构化埋点事件（D39 三块）。payload 不含对话原文流水；后端入库前会再脱敏。 */
export function postAnalyticsEvent(event: AnalyticsEventCreate): Promise<AnalyticsEvent> {
  return apiPost<AnalyticsEvent>('/analytics/events', event);
}

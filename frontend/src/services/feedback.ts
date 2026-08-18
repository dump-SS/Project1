/**
 * 建议与复盘的有用性反馈 —— 数据提交。
 *
 * 接口映射（docs/openapi.yaml）：
 * - PUT /recommendations/{recommendationId}/feedback  建议反馈（rating: useful/neutral/not_useful）
 * - PUT /summaries/{summaryId}/feedback               复盘反馈（同 RatingFeedback）
 *
 * 两条接口语义一致：一条建议/复盘至多一份反馈，用户改主意即覆盖（PUT 幂等）。
 */

import { apiPut } from './http';
import type {
  Rating,
  RecommendationFeedbackResult,
  SummaryFeedbackResult,
} from '@/types/api';

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

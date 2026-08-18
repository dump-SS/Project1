/**
 * 个性化建议（PRD 5.3）—— 数据获取。
 *
 * 接口映射（openapi.yaml 6.x）：
 * - GET  /recommendations                      建议列表（按时间倒序，分页）
 * - POST /recommendations                      手动请求生成建议（202 RecommendationPending）
 * - GET  /recommendations/{recommendationId}   建议详情（pending → ready/failed 轮询）
 * - PUT  /recommendations/{recommendationId}/feedback 提交「准不准/有没有用」轻量反馈
 *
 * 生成是异步的：POST 只受理（status=pending），需要前端轮询 GET 详情，
 * 直到 generation.status 进入终态（ready / failed）。
 */

import { apiGet, apiPost, apiPut } from './http';
import type {
  Rating,
  RecScene,
  Recommendation,
  RecommendationCreate,
  RecommendationFeedbackResult,
  RecommendationList,
  RecommendationPending,
  Subject,
} from '@/types/api';

/** 建议列表；默认只取 ready（生成完成），可按学科/场景过滤。 */
export function listRecommendations(
  query: { scene?: RecScene; subject?: Subject; status?: 'ready' | 'all'; page?: number; pageSize?: number } = {},
  signal?: AbortSignal,
): Promise<RecommendationList> {
  return apiGet<RecommendationList>('/recommendations', query, signal);
}

/** 手动请求生成建议（scene 必填；post_session 场景建议必传 subject）。 */
export function createRecommendation(body: RecommendationCreate): Promise<RecommendationPending> {
  return apiPost<RecommendationPending>('/recommendations', body);
}

/** 拉取建议详情；生成未完成时 generation.status 仍为 pending、items 为 null。 */
export function getRecommendation(recommendationId: string, signal?: AbortSignal): Promise<Recommendation> {
  return apiGet<Recommendation>(`/recommendations/${recommendationId}`, undefined, signal);
}

/** 提交建议反馈（rating 必填，reason 可选 ≤100 字；重复提交覆盖）。 */
export function submitRecommendationFeedback(
  recommendationId: string,
  rating: Rating,
  reason?: string,
): Promise<RecommendationFeedbackResult> {
  return apiPut<RecommendationFeedbackResult>(`/recommendations/${recommendationId}/feedback`, {
    rating,
    reason: reason?.trim() ? reason.trim() : null,
  });
}

/** 建议生成是否已到终态（生成完成 / 生成失败）。 */
export function isRecommendationTerminal(status: string | undefined): boolean {
  return status === 'ready' || status === 'failed';
}

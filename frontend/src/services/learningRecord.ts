/**
 * 学习记录与个性化建议 —— 数据提交与轮询。
 *
 * 接口映射（docs/openapi.yaml）：
 * - POST /learning-records         提交学习记录（同步回状态快照 + 建议句柄）
 * - GET  /recommendations/{id}     轮询建议生成结果
 *
 * 建议由提交记录接口自动触发（RecordInput.skipRecommendation 默认 false），
 * 前端拿到 recommendation.recommendationId 后只需轮询 GET，无需手动调用 POST /recommendations。
 */

import { apiGet, apiPost } from './http';
import type { LearningRecordCreated, Recommendation, RecordInput } from '@/types/api';

export function createLearningRecord(record: RecordInput): Promise<LearningRecordCreated> {
  return apiPost<LearningRecordCreated>('/learning-records', record);
}

export function getRecommendation(recommendationId: string): Promise<Recommendation> {
  return apiGet<Recommendation>(`/recommendations/${recommendationId}`);
}

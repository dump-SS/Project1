/**
 * 学习记录与个性化建议 —— 数据提交与轮询。
 *
 * 接口映射（docs/openapi.yaml）：
 * - POST /learning-records             提交学习记录（同步回状态快照 + 建议句柄）
 * - GET  /learning-records             记录列表（按学科 / 日期范围过滤，分页）
 * - DELETE /learning-records/{recordId} 删除记录并触发窗口重算
 * - GET  /recommendations/{recommendationId}  轮询建议生成结果
 *
 * 建议由提交记录接口自动触发（RecordInput.skipRecommendation 默认 false），
 * 前端拿到 recommendation.recommendationId 后只需轮询 GET，无需手动调用 POST /recommendations。
 */

import { apiDelete, apiGet, apiGetAllPages, apiPost } from './http';
import type {
  LearningRecord,
  LearningRecordCreated,
  LearningRecordDeleted,
  Recommendation,
  RecordInput,
  Subject,
} from '@/types/api';

export function createLearningRecord(record: RecordInput): Promise<LearningRecordCreated> {
  return apiPost<LearningRecordCreated>('/learning-records', record);
}

export function getRecommendation(recommendationId: string): Promise<Recommendation> {
  return apiGet<Recommendation>(`/recommendations/${recommendationId}`);
}

/**
 * 拉取学习记录列表。对应 `GET /api/v1/learning-records`（openapi.yaml listLearningRecords）。
 * 默认走全量分页（apiGetAllPages），跨月查询不会被截断；调用方按需传 subject / dateFrom / dateTo。
 */
export function listLearningRecords(
  query: { subject?: Subject; dateFrom?: string; dateTo?: string } = {},
  signal?: AbortSignal,
): Promise<LearningRecord[]> {
  return apiGetAllPages<LearningRecord>('/learning-records', query, signal);
}

/**
 * 删除学习记录。对应 `DELETE /api/v1/learning-records/{recordId}`。
 * 服务端在删除后同步重算当前窗口，响应带回重算后的状态快照（recalculatedAssessment），
 * 调用方可用它来局部更新当日卡片，无需再发一次 GET /assessments/current。
 */
export function deleteLearningRecord(
  recordId: string,
  signal?: AbortSignal,
): Promise<LearningRecordDeleted> {
  return apiDelete<LearningRecordDeleted>(`/learning-records/${recordId}`, signal);
}

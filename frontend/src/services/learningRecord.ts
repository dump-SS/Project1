/**
 * 学习记录与个性化建议 —— 数据提交与轮询。
 *
 * 接口映射（docs/openapi.yaml v1.7.1）：
 * - POST   /learning-records              提交学习记录（同步回状态快照 + 建议句柄）
 * - GET    /learning-records              记录列表（按学科 / 来源 / 日期范围过滤，分页）
 * - PATCH  /learning-records/{recordId}   事后回写（D15：正确率/完成度/自评/备注）
 * - DELETE /learning-records/{recordId}   删除记录并触发窗口重算
 * - GET    /recommendations/{recommendationId}  轮询建议生成结果
 *
 * 建议由提交记录接口自动触发（RecordInput.skipRecommendation 默认 false），
 * 前端拿到 recommendation.recommendationId 后只需轮询 GET，无需手动调用 POST /recommendations。
 */

import { apiDelete, apiGet, apiGetAllPages, apiPatch, apiPost } from './http';
import type {
  LearningRecord,
  LearningRecordCreated,
  LearningRecordDeleted,
  Recommendation,
  RecordInput,
  Subject,
} from '@/types/api';
import type { Completion, SelfReportInput } from './timer';

export function createLearningRecord(record: RecordInput): Promise<LearningRecordCreated> {
  return apiPost<LearningRecordCreated>('/learning-records', record);
}

/**
 * 事后回写（D15）：学习记录是「可事后回写的活实体」，不是「提交即封存」的快照。
 *
 * **语义（很重要）**：只在字段被**显式传入**时才改。
 * `accuracy: null` = 清空（"确实没填"）；**不传** = 不动。两者必须区分，
 * 否则用户只想补个备注会把正确率抹掉。
 *
 * 回写会重算状态快照，但**不会重复触发建议生成**——补个正确率不该再推一条建议给用户。
 *
 * ⚠️ 类型定义（RecordUpdateInput）随 openapi v1.7.1 新增，暂放本文件而不动
 * `types/api.ts`（该文件按板块契约归 X1 管），等 X1 收口时合并过去。
 */
export interface RecordUpdateInput {
  completion?: Completion;
  /** 显式传 null = 清空；不传 = 不动 */
  accuracy?: number | null;
  note?: string | null;
  /** 整体覆盖自评四字段（不支持局部改） */
  selfReport?: SelfReportInput;
}

export interface LearningRecordUpdated {
  record: LearningRecord & {
    /** 记录来源（D49）：self_report=用户自评产生；exam=考试成绩回填生成 */
    source?: 'self_report' | 'exam';
    sourceExamId?: string | null;
  };
  recalculatedAssessment: {
    assessmentId?: string | null;
    subject: Subject;
    windowScore?: number | null;
    trend?: string | null;
    stateLabel: string;
    dataSufficient: boolean;
    recordCount: number;
  };
}

export function updateLearningRecord(
  recordId: string,
  body: RecordUpdateInput,
  signal?: AbortSignal,
): Promise<LearningRecordUpdated> {
  return apiPatch<LearningRecordUpdated>(`/learning-records/${recordId}`, body, signal);
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

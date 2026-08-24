/**
 * 板块二 · 知识点掌握服务（v2.1）
 *
 * 对接 /api/v1/mastery/*。样本 <3 时 mastery=null、dataSufficient=false。
 */

import { apiGet } from './http';

export interface PointMasteryResult {
  pointId: string;
  mastery: number | null;
  dataSufficient: boolean;
  sampleSize: number;
  factors?: Record<string, number>;
  updatedAt?: string;
}

export interface SubjectMasteryResult {
  subjectCode: string;
  mastery: number | null;
  dataSufficient: boolean;
  sampleSize: number;
  points: Array<PointMasteryResult & { examWeight?: number }>;
}

/** GET /mastery/points/{pointId} 单点掌握度 */
export function fetchPointMastery(pointId: string): Promise<PointMasteryResult> {
  return apiGet(`/mastery/points/${pointId}`);
}

/** GET /mastery/subjects/{code} 学科聚合掌握度 */
export function fetchSubjectMastery(subjectCode: string): Promise<SubjectMasteryResult> {
  return apiGet(`/mastery/subjects/${subjectCode}`);
}

/** GET /mastery/subjects/{code}/timeline 时间序列（v2.2） */
export function fetchMasteryTimeline(subjectCode: string): Promise<{
  subjectCode: string;
  items: Array<{ date: string; mastery: number | null; sampleSize: number }>;
}> {
  return apiGet(`/mastery/subjects/${subjectCode}/timeline`);
}

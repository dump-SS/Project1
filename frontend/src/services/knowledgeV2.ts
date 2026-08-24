/**
 * 板块二 · 知识库服务（v2.1 转正）
 *
 * 对接真实后端 /api/v1/knowledge/*（docs/openapi.yaml v1.5 学科知识库段）。
 * 全部走 http.ts 统一封装；后端未就绪时抛 ApiError，UI 层按 localFallback 降级。
 */

import { apiGet } from './http';

/* ============ 类型（对齐 openapi.yaml v1.5） ============ */

export interface KnowledgeSubject {
  subjectCode: string;
  name: string;
  gradeBand?: string | null;
  pointCount: number;
  version: string;
}

export interface KnowledgePoint {
  pointId: string;
  subjectCode: string;
  code: string;
  name: string;
  definition: string;
  parentId?: string | null;
  difficulty: number;
  examWeight: number;
  errorTip?: string | null;
}

export interface KnowledgePointRelation {
  srcPointId: string;
  dstPointId: string;
  type: 'prerequisite' | 'derived' | 'contrast' | 'applied_in';
  weight?: number | null;
}

export interface KnowledgePointDetail extends KnowledgePoint {
  relations: KnowledgePointRelation[];
}

export interface KnowledgePointMatch {
  pointId: string;
  name: string;
  subjectCode: string;
  confidence: number;
  matchedBy: 'embedding' | 'keyword_fallback';
}

/* ============ 接口 ============ */

/** GET /knowledge/subjects 已启用学科列表 */
export async function fetchKnowledgeSubjects(): Promise<KnowledgeSubject[]> {
  const res = await apiGet<{ items: KnowledgeSubject[] }>('/knowledge/subjects');
  return res.items;
}

/** GET /knowledge/subjects/{code}/points 学科知识点树 */
export async function fetchKnowledgePoints(subjectCode: string): Promise<KnowledgePoint[]> {
  const res = await apiGet<{ items: KnowledgePoint[] }>(
    `/knowledge/subjects/${subjectCode}/points`,
  );
  return res.items;
}

/** GET /knowledge/points/{pointId} 单点详情 */
export async function fetchKnowledgePoint(pointId: string): Promise<KnowledgePointDetail> {
  return apiGet<KnowledgePointDetail>(`/knowledge/points/${pointId}`);
}

/** GET /knowledge/subjects/{code}/graph 图谱（v2.1 树形占位，v2.3 关系边 + 薄弱路径） */
export async function fetchKnowledgeGraph(subjectCode: string): Promise<{
  subjectCode: string;
  nodes: KnowledgePoint[];
  edges: KnowledgePointRelation[];
  weakPointIds?: string[];
}> {
  return apiGet(`/knowledge/subjects/${subjectCode}/graph`);
}

/** GET /knowledge/points/match 文本 → 候选知识点 */
export async function matchKnowledgePoints(
  text: string,
  subject?: string,
  limit = 5,
): Promise<{ items: KnowledgePointMatch[]; matchedBy: string }> {
  return apiGet('/knowledge/points/match', { text, subject, limit });
}

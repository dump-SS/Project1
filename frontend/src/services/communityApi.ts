/**
 * 板块三 · 真实接口服务（M4 转正，决策 v1.7 §4.11）
 *
 * 服务端抽取为唯一真源：客户端不上传特征值。
 * - GET /me/community-consent   授权状态
 * - PUT /me/community-consent   开启/撤回（显式授权动作）
 * - GET /community/aggregate    只读服务端聚合（stage + metric 必填）
 */
import { apiGet, apiPut } from './http';

export interface CommunityConsent {
  enabled: boolean;
  autoParticipate: boolean;
  updatedAt: string;
}

export interface CommunityHistogramBucket {
  lo: number;
  hi: number | null;
  count: number;
}

export interface CommunityAggregate {
  stage: 'junior' | 'senior';
  metric: 'hours' | 'focus' | 'fatigue' | 'completion';
  period: string;
  poolSize: number;
  percentiles: { p25: number; p50: number; p75: number };
  histogram: CommunityHistogramBucket[];
  computedAt: string;
}

export type CommunityStage = 'junior' | 'senior';
export type CommunityMetric = 'hours' | 'focus' | 'fatigue' | 'completion';

export function fetchCommunityConsent(): Promise<CommunityConsent> {
  return apiGet<CommunityConsent>('/me/community-consent');
}

export function putCommunityConsent(enabled: boolean, autoParticipate?: boolean): Promise<CommunityConsent> {
  return apiPut<CommunityConsent>('/me/community-consent', { enabled, autoParticipate });
}

export function fetchCommunityAggregate(
  stage: CommunityStage,
  metric: CommunityMetric,
): Promise<CommunityAggregate> {
  return apiGet<CommunityAggregate>('/community/aggregate', { stage, metric });
}

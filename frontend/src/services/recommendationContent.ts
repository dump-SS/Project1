/**
 * 导学计划页推荐内容 —— 数据获取。
 *
 * 接口：GET /api/v1/recommendation-content
 * 数据量不足时返回 eligible=false，前端隐藏推荐块并显示占位说明。
 */

import { apiGet } from './http';

export interface RecommendationContent {
  eligible: boolean;
  recordCount: number;
  recentWindowDays: number;
  subject: string | null;
  topic: string | null;
  reason: string;
  fromLLM: boolean;
}

const CACHE_KEY = 'rec_content';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24h

interface CachedEntry {
  data: RecommendationContent;
  cachedAt: number;
}

function readCache(): CachedEntry | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedEntry;
    if (Date.now() - parsed.cachedAt > CACHE_TTL_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(data: RecommendationContent) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ data, cachedAt: Date.now() }));
  } catch {
    // 隐私模式/配额满时写失败属预期，不影响主流程
  }
}

export async function fetchRecommendationContent(signal?: AbortSignal): Promise<RecommendationContent> {
  try {
    const data = await apiGet<RecommendationContent>('/recommendation-content', undefined, signal);
    writeCache(data);
    return data;
  } catch {
    // 接口失败：返回 last-known（不展示 LLM 标记，让用户感知"本次无数据"）
    const cached = readCache();
    if (cached) return cached.data;
    return {
      eligible: false,
      recordCount: 0,
      recentWindowDays: 7,
      subject: null,
      topic: null,
      reason: '推荐服务暂不可用',
      fromLLM: false,
    };
  }
}

/**
 * 复盘（学习总结）—— 数据获取。
 *
 * 接口映射（docs/openapi.yaml）：
 * - GET /summaries  复盘列表（按 periodEnd 倒序）
 */

import { apiGet } from './http';
import type { SummaryList, Summary } from '@/types/api';

export function listSummaries(signal?: AbortSignal): Promise<SummaryList> {
  return apiGet<SummaryList>('/summaries', { page: 1, pageSize: 5 }, signal);
}

/** 获取最新一条已生成的复盘 */
export async function fetchLatestSummary(signal?: AbortSignal): Promise<Summary | null> {
  const result = await listSummaries(signal);
  const ready = result.items.find((s) => s.generation.status === 'ready' && s.content);
  return ready ?? null;
}
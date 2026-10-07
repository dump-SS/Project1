/**
 * 搜题（D24 三态）+ 讲解归档（D52）—— D 板块知识页两条链路。
 *
 * 对应契约 v1.7.1 的 `SearchArchive` / `Explanation` / `SearchMode` / `ExplanationMode`。
 *
 * 两条链路**不合并**：搜题是「解一道题」，讲解是「讲透一个概念」，语义不同，
 * 归档分开存（§3.8.4）。
 *
 * 出域（2026-09-30 拍板）：题面是用户自己的内容、且由用户当场发起，
 * 属于 `user_error_content`，允许发给云端模型；但受三道约束——
 * ① 每次点击即一次授权（后端不做后台/预生成）；
 * ② 用户可在设置里关闭（关闭后只发知识点聚合字段，题面不出域）；
 * ③ 出域留痕。前端的责任是把「开关状态」如实告诉用户，别让开关形同虚设。
 */

import { apiGet, apiPost } from './http';

/* ============ 搜题三态（D24） ============ */

export type SearchMode = 'direct' | 'analytic' | 'guided';

/** 三态的人话解释——用户切换时要看得懂差别 */
export const SEARCH_MODE_LABEL: Record<SearchMode, string> = {
  direct: '直给',
  analytic: '解析式',
  guided: '引导式',
};

export const SEARCH_MODE_HINT: Record<SearchMode, string> = {
  direct: '一次给完整解答，适合赶时间',
  analytic: '按步骤讲清每一步为什么这么走',
  guided: '不给答案，先给提示让你自己走一步',
};

/** 知识引用协议卡片（文本已冻结，四个字段，前端不得自行扩展） */
export interface KnowledgeRef {
  pointId: string | null;
  subjectCode: string | null;
  name: string;
  /** null 表示样本不足，**不是 0**；展示时要写「积累中」而不是「0%」 */
  mastery: number | null;
}

export interface SearchArchive {
  archiveId: string;
  subject: string | null;
  rawText: string;
  solution: string | null;
  mode: SearchMode | null;
  pointIds: KnowledgeRef[];
  /** 多解（≤3），默认只有主解；主解即 solution */
  solutions: string[];
  solutionCount: number;
  createdAt: string;
}

export interface SearchArchiveList {
  items: SearchArchive[];
  pagination: { total: number; limit: number; offset: number };
}

/**
 * POST /api/v1/search-archives —— 发起搜题。
 *
 * ⚠️ 这就是「用户点击」本身。后端同步生成，不做预生成、不排队。
 * mode 不传时后端沿用上次选择（三态被记忆），所以这里允许 undefined。
 */
export function createSearchArchive(
  payload: { subject?: string; rawText: string; mode?: SearchMode },
  signal?: AbortSignal,
): Promise<SearchArchive> {
  return apiPost<SearchArchive>('/search-archives', payload, signal);
}

export function listSearchArchives(
  params: { subject?: string; mode?: SearchMode; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<SearchArchiveList> {
  return apiGet<SearchArchiveList>('/search-archives', { ...params }, signal);
}

export function getSearchArchive(archiveId: string, signal?: AbortSignal): Promise<SearchArchive> {
  return apiGet<SearchArchive>(`/search-archives/${encodeURIComponent(archiveId)}`, undefined, signal);
}

/* ============ 讲解（D52） ============ */

export type ExplanationMode = 'original' | 'regenerated';

export interface Explanation {
  explanationId: string;
  pointId: string | null;
  subject: string | null;
  mode: ExplanationMode;
  content: string;
  /** true = 预制入库的精品样例（长期保存），与动态生成严格区分 */
  isCurated: boolean;
  createdAt: string;
}

export interface ExplanationList {
  items: Explanation[];
  pagination: { total: number; limit: number; offset: number };
}

/**
 * POST /api/v1/explanations —— 讲解两态并存。
 *
 * `original` = 回顾取原文（不调模型，取上次那条；讲法一致才有价值）；
 * `regenerated` = 重新讲、现生成一条。两条都留在归档里，不互相顶掉。
 */
export function createExplanation(
  payload: { pointId?: string | null; subject?: string; mode: ExplanationMode },
  signal?: AbortSignal,
): Promise<Explanation> {
  return apiPost<Explanation>('/explanations', payload, signal);
}

export function listExplanations(
  params: { pointId?: string; subject?: string; isCurated?: boolean; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<ExplanationList> {
  return apiGet<ExplanationList>('/explanations', { ...params }, signal);
}

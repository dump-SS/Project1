/**
 * 板块二 · 知识库相关接口封装（演示用）。
 *
 * 真实后端在 v2.1/v2.2 阶段实现，本文件先按契约声明入参/出参。
 * 现阶段后端未上线，所有调用都会因网络层失败抛出 ApiError，
 * 由 UI 层捕获并 toast 提示。
 */

import { apiPost } from './http';

/* ============ 复盘生成 ============ */

export interface KnowledgeSummaryPayload {
  subject: string;
  period: string;
  error_summary: string;
  mastery_changes: string;
  state_context: string;
}

export interface KnowledgeSummaryResponse {
  summary: string;
  /** 是否来自 LLM；false 即规则模板降级 */
  from_llm?: boolean;
  /** 生成时间 ISO 串 */
  generated_at?: string;
}

/** POST /api/knowledge-summary —— 学科阶段复盘 */
export function generateKnowledgeSummary(
  payload: KnowledgeSummaryPayload,
  signal?: AbortSignal,
): Promise<KnowledgeSummaryResponse> {
  return apiPost<KnowledgeSummaryResponse>('/knowledge-summary', payload, signal);
}

/* ============ AI 解析 ============ */

export interface ErrorParsePayload {
  question_text: string;
  student_answer?: string;
  correct_answer?: string;
  matched_knowledge?: {
    name: string;
    definition: string;
    error_tip: string;
  };
}

export interface ErrorParseResponse {
  /** markdown / 纯文本均可；前端直接渲染 */
  explanation: string;
  /** 关键步骤（可选） */
  steps?: string[];
  /** 复习建议（可选） */
  review_suggestion?: string;
  from_llm?: boolean;
}

/** POST /api/error-parse —— 单题 AI 解析 */
export function parseError(payload: ErrorParsePayload, signal?: AbortSignal): Promise<ErrorParseResponse> {
  return apiPost<ErrorParseResponse>('/error-parse', payload, signal);
}

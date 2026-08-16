/**
 * HTTP 封装。所有 service 统一走这里，不要在组件里直接 fetch。
 *
 * 基础路径与鉴权方式对应 openapi.yaml：
 *   servers.url = /api/v1
 *   securitySchemes.bearerAuth = Authorization: Bearer <token>
 */

import type { ApiErrorBody, Pagination } from '@/types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const TOKEN = import.meta.env.VITE_API_TOKEN ?? '';

/** openapi.yaml 0.2 节的统一错误格式 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field?: string;

  constructor(status: number, code: string, message: string, field?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

type QueryValue = string | number | boolean | undefined | null;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        search.append(key, String(value));
      }
    }
  }
  const qs = search.toString();
  return `${BASE_URL}${path}${qs ? `?${qs}` : ''}`;
}

export async function apiGet<T>(
  path: string,
  query?: Record<string, QueryValue>,
  signal?: AbortSignal,
): Promise<T> {
  const headers: HeadersInit = { Accept: 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;

  const response = await fetch(buildUrl(path, query), { method: 'GET', headers, signal });

  if (!response.ok) {
    let code = 'INTERNAL_ERROR';
    let message = `请求失败（HTTP ${response.status}）`;
    let field: string | undefined;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        field = body.error.field;
      }
    } catch {
      // 后端还没上线时通常返回 HTML 404 页，解析失败属预期，沿用默认文案
    }
    throw new ApiError(response.status, code, message, field);
  }

  return (await response.json()) as T;
}

/**
 * 分页拉取全部数据。
 * openapi.yaml 约定 pageSize 上限 50，跨月查询时单页装不下，这里按页累加。
 * maxPages 是保险丝，避免后端 total 异常时打成死循环。
 */
export async function apiGetAllPages<T>(
  path: string,
  query: Record<string, QueryValue>,
  signal?: AbortSignal,
  maxPages = 10,
): Promise<T[]> {
  const pageSize = 50;
  const collected: T[] = [];
  let page = 1;

  while (page <= maxPages) {
    const result = await apiGet<{ items: T[]; pagination: Pagination }>(
      path,
      { ...query, page, pageSize },
      signal,
    );

    collected.push(...result.items);

    const total = result.pagination?.total ?? collected.length;
    if (collected.length >= total || result.items.length === 0) break;
    page += 1;
  }

  return collected;
}

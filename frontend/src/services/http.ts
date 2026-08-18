/**
 * HTTP 封装。所有 service 统一走这里，不要在组件里直接 fetch。
 *
 * 基础路径与鉴权方式对应 openapi.yaml：
 *   servers.url = /api/v1
 *   securitySchemes.sessionCookie = HttpOnly Session Cookie（sid），credentials: 'include'
 *
 * 鉴权由 AuthContext 在登录时建立（authApi.js 走 Cookie），
 * 这里只需 credentials: 'include' 让浏览器自动携带 sid，无需手动设置 Authorization 头。
 */

import type { ApiErrorBody, Pagination } from '@/types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

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

/** 网络层失败判别：true 表示「接口不可达」（无 HTTP 状态），区别于接口返回的 4xx/5xx 业务错误 */
export function isNetworkError(err: unknown): boolean {
  const status = (err as { status?: number })?.status;
  return status === undefined || status === 0;
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

export async function apiPost<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: HeadersInit = { 'Content-Type': 'application/json', Accept: 'application/json' };

  const response = await fetch(buildUrl(path), {
    method: 'POST',
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    let code = 'INTERNAL_ERROR';
    let message = `请求失败（HTTP ${response.status}）`;
    let field: string | undefined;
    try {
      const errBody = (await response.json()) as ApiErrorBody;
      if (errBody?.error) {
        code = errBody.error.code ?? code;
        message = errBody.error.message ?? message;
        field = errBody.error.field;
      }
    } catch {
      // 后端未上线时返回非 JSON，解析失败属预期
    }
    throw new ApiError(response.status, code, message, field);
  }

  return (await response.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  idempotencyKey?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const response = await fetch(buildUrl(path), {
    method: 'PATCH',
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    let code = 'INTERNAL_ERROR';
    let message = `请求失败（HTTP ${response.status}）`;
    let field: string | undefined;
    try {
      const errBody = (await response.json()) as ApiErrorBody;
      if (errBody?.error) {
        code = errBody.error.code ?? code;
        message = errBody.error.message ?? message;
        field = errBody.error.field;
      }
    } catch {
      // 后端未上线时返回非 JSON，解析失败属预期
    }
    throw new ApiError(response.status, code, message, field);
  }

  return (await response.json()) as T;
}

export async function apiPut<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };

  const response = await fetch(buildUrl(path), {
    method: 'PUT',
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    let code = 'INTERNAL_ERROR';
    let message = `请求失败（HTTP ${response.status}）`;
    let field: string | undefined;
    try {
      const errBody = (await response.json()) as ApiErrorBody;
      if (errBody?.error) {
        code = errBody.error.code ?? code;
        message = errBody.error.message ?? message;
        field = errBody.error.field;
      }
    } catch {
      // 后端未上线时返回非 JSON，解析失败属预期
    }
    throw new ApiError(response.status, code, message, field);
  }

  return (await response.json()) as T;
}

export async function apiGet<T>(
  path: string,
  query?: Record<string, QueryValue>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(buildUrl(path, query), {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'include',
    signal,
  });

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
 *
 * maxPages 只是防止后端 total 异常时打成死循环的保险丝，不应成为静默截断数据的上限——
 * 之前设为 10（最多 500 条）会让高频用户的月度记录被悄悄丢掉，导致学科占比、
 * 时长趋势等聚合结果失真。这里放到 200 页（1 万条，远超任何真实用户的单次查询量），
 * 真触顶时打印告警，把"沉默的数据错误"变成"可见的信号"。
 */
export async function apiGetAllPages<T>(
  path: string,
  query: Record<string, QueryValue>,
  signal?: AbortSignal,
  maxPages = 200,
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

    if (page > maxPages) {
      // eslint-disable-next-line no-console
      console.warn(
        `[apiGetAllPages] ${path} 达到 ${maxPages} 页上限仍未取完（已取 ${collected.length}/${total}），数据可能被截断`,
      );
    }
  }

  return collected;
}

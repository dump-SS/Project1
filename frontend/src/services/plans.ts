/**
 * 学习计划 —— 生成。对应 openapi.yaml「2.1 createPlan」(POST /plans)，流程环节②。
 * 该接口由服务端规则引擎同步返回，不走 LLM（PRD 8.2：AI 不可用时仍能看计划）。
 * 新用户无历史数据时响应里 adaptedFrom 为 null，走规则模板。
 */
import { apiPost, isNetworkError } from './http';
import { cacheGet, cacheSet } from './localFallback';
import type { Plan } from '@/types/api';

/** localStorage 最近一次成功计划缓存 key */
export const LAST_PLAN_CACHE_KEY = 'plan:last';

export interface PlanCreatePayload {
  /** 计划归属日期 YYYY-MM-DD */
  planDate: string;
  /** 本次可用学习时间，10-600 分钟 */
  availableMinutes: number;
  /** 可选，关联目标；不传则使用全部 active 目标 */
  goalIds?: string[];
  /** 可选，默认 false；true 覆盖当日已有计划 */
  regenerate?: boolean;
}

export interface CreatePlanResult {
  plan: Plan;
  /** true 表示本次是「接口不可达」时回退到了上次成功缓存，而非新生成的计划 */
  fromCache: boolean;
}

export async function createPlan(payload: PlanCreatePayload): Promise<CreatePlanResult> {
  try {
    const plan = await apiPost<Plan>('/plans', payload);
    cacheSet(LAST_PLAN_CACHE_KEY, plan);
    return { plan, fromCache: false };
  } catch (err) {
    // 仅网络层失败（接口不可达）时降级到上次成功缓存；业务错误（4xx/5xx）总是上抛
    if (isNetworkError(err)) {
      const cached = cacheGet(LAST_PLAN_CACHE_KEY) as Plan | null;
      if (cached) return { plan: cached, fromCache: true };
    }
    throw err;
  }
}

/** 本地时间（非 UTC）的 YYYY-MM-DD，作为 planDate 默认值 */
export function localDateString(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
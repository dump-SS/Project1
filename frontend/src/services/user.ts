/**
 * 用户资料（openapi.yaml 0.5 节 /me）—— 数据获取。
 *
 * 接口映射：
 * - GET  /me   获取当前用户资料（含 onboardingCompleted，用于判断是否需要引导建档）
 * - PUT  /me   初始化建档（幂等，字段全必填）
 * - PATCH /me  局部更新（字段全可选）
 */

import { apiGet, apiPatch, apiPut } from './http';
import type { User, UserProfilePatch, UserProfilePut } from '@/types/api';

export function getMe(signal?: AbortSignal): Promise<User> {
  return apiGet<User>('/me', undefined, signal);
}

/** 初始化建档（stage / grade / subjects 全必填）。 */
export function putMe(body: UserProfilePut): Promise<User> {
  return apiPut<User>('/me', body);
}

/** 局部更新用户资料（字段全可选）。 */
export function patchMe(body: UserProfilePatch): Promise<User> {
  return apiPatch<User>('/me', body);
}

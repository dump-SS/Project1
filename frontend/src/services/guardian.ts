/**
 * 监护人授权（PRD 8.1 合规底线）—— 数据获取。
 *
 * 接口映射（openapi.yaml 0.5 节）：
 * - POST   /me/guardian-authorization  提交监护人联系方式并发送确认请求（202，返回 confirmToken）
 * - GET    /guardian-authorization/confirm  监护人点链接确认（无需登录，?token=…）
 * - DELETE /me/guardian-authorization  撤销授权（204，账号进入只读）
 * - 授权状态（pending/active/revoked/expired）来自 GET /me 的 guardianAuthorization
 */

import { apiDelete, apiGet, apiPost } from './http';
import type { GuardianAuthorizationRequest, GuardianAuthorizationSubmission } from '@/types/api';

/** 提交监护人联系方式（邮箱/手机号二选一），返回确认 token。 */
export function submitGuardianAuthorization(
  body: GuardianAuthorizationRequest,
): Promise<GuardianAuthorizationSubmission> {
  return apiPost<GuardianAuthorizationSubmission>('/me/guardian-authorization', body);
}

/** 监护人点击链接确认授权（无需登录）。返回 ok=false 表示 token 无效或已使用。 */
export function confirmGuardianAuthorization(token: string): Promise<{ ok: boolean }> {
  return apiGet<{ ok: boolean }>('/guardian-authorization/confirm', { token });
}

/**
 * 构造确认链接（完整绝对地址）。
 * MVP 演示期后端不真发邮件，靠此链接让演示者可点击/复制打开真实确认链路（无需登录）。
 */
export function buildGuardianConfirmUrl(token: string): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
  return `${window.location.origin}${base}/guardian-authorization/confirm?token=${encodeURIComponent(token)}`;
}

/** 撤销监护人授权（账号进入只读）。 */
export function revokeGuardianAuthorization(): Promise<void> {
  return apiDelete<void>('/me/guardian-authorization');
}
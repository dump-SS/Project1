/**
 * 监护人授权（PRD 8.1 合规底线）—— 数据获取。
 *
 * 接口映射（openapi.yaml 0.5 节）：
 * - POST   /me/guardian-authorization  提交监护人联系方式并发送确认请求（202）
 * - DELETE /me/guardian-authorization  撤销授权（204，账号进入只读）
 * - 授权状态（pending/active/revoked/expired）来自 GET /me 的 guardianAuthorization
 */

import { apiDelete, apiPost } from './http';
import type { GuardianAuthorizationRequest } from '@/types/api';

/** 提交监护人联系方式（邮箱/手机号二选一），返回后等待监护人点击链接确认。 */
export function submitGuardianAuthorization(body: GuardianAuthorizationRequest): Promise<void> {
  return apiPost<void>('/me/guardian-authorization', body);
}

/** 撤销监护人授权（账号进入只读）。 */
export function revokeGuardianAuthorization(): Promise<void> {
  return apiDelete<void>('/me/guardian-authorization');
}

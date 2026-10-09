/**
 * 用量与治理读取服务 —— G 板块。
 *
 * 接口映射（docs/openapi.yaml v1.7.0，tag「pilot 运营与治理」）：
 * - GET /me/usage        月度用量流水与合计（只读，无任何支付语义）
 * - GET /me/medals       已获得奖章（#49 最小版）
 * - GET /me/violations   本人违规处置留痕（#43）
 */

import { apiGet } from './http';
import type { MedalList, UsageLedgerList, ViolationLogList } from '@/types/governance';

/**
 * 查询月度用量。month 缺省时后端返回当前月。
 * @param month "YYYY-MM"
 */
export function getMyUsage(month?: string): Promise<UsageLedgerList> {
  return apiGet<UsageLedgerList>('/me/usage', month ? { month } : undefined);
}

export function getMyMedals(): Promise<MedalList> {
  return apiGet<MedalList>('/me/medals');
}

export function getMyViolations(): Promise<ViolationLogList> {
  return apiGet<ViolationLogList>('/me/violations');
}

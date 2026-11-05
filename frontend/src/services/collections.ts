/**
 * 收藏写入 —— 对应 openapi.yaml v1.16.0「POST /me/collection/items」（E 板块，dev-4 交付）。
 *
 * ⚠️ 范围说明：本文件只封装 **#47 摘要进收藏** 需要的「新建条目」一个调用
 * （F 的摘要卡是它的第一个消费者）。收藏列表/分组/虚化等完整前端归 E/dev8——
 * dev8 的 `services/collection.ts`（collectItem，对话消息收藏）是另一条链路；
 * 那边建正式 collectionApi 时可把这里并入或替换，接口形状以契约为准。
 *
 * sourceRef.type='upload_summary' 在契约 v1.16.0 的枚举里已预留（CollectionSourceRef）。
 */
import { apiPost } from './http';

export interface CollectionSnapshotInput {
  content: string;
  /** 契约枚举 markdown / plain…；默认 markdown */
  format?: string;
}

export interface CollectionSourceRefInput {
  type: string;
  refId?: string | null;
  label?: string | null;
  subject?: string;
}

export interface CollectionItemCreateInput {
  collectionId?: string | null;
  title?: string | null;
  snapshot: CollectionSnapshotInput;
  sourceRef?: CollectionSourceRefInput;
}

/**
 * 新增收藏条目。同一条内容反复收藏 → 服务端覆盖并返回建档后的条目（#52），
 * 前端只需提示「已存入收藏」。
 */
export async function createCollectionItem(
  payload: CollectionItemCreateInput,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>('/me/collection/items', payload, signal);
}

/**
 * E 板块 · 收藏服务（契约 v1.17.1，9 个操作）
 *
 * 对接 /api/v1/me/collection*。设计口径见 docs/product-redesign-target.md §4.8：
 * - 第 803 行（§4.8.2）：**存快照不存引用**——原文到期即删，只存引用会变死链
 * - 第 815 行（§4.8.3）：自定义分组是标签字段、内置分组是筛选维度，两者正交
 * - 第 817 行（§4.8.3）：展现为卡片 + 来源引用，不做文本直列
 * - 第 821-827 行（§4.8.4）：内容不可编辑，只有高亮与「虚化」两种标记；虚化状态需持久化
 * - 第 828 行（#52）：同一条内容反复收藏 → 覆盖，并给轻提示「已更新这个收藏」
 *
 * ⚠️ 判断「建档还是覆盖」只能用 POST 响应里的 `created`。建档与覆盖同为 201，
 * 而 `updatedAt` 靠不住：SQLite 的时间戳只有秒级精度（同一秒内覆盖时等于 createdAt），
 * 且覆盖分支在 body 未带可变字段时不产生 UPDATE、updated_at 根本不动。
 */

import type { Subject } from '@/types/api';
import { apiDelete, apiGet, apiPatch, apiPost } from './http';

/** 快照正文格式。前端据此决定是否渲染 markdown，不要靠正则嗅探（契约 CollectionSnapshot.format） */
export type CollectionSnapshotFormat = 'markdown' | 'plain';

/** 来源类型（契约 CollectionSourceRef.type，取值不得另造） */
export type CollectionSourceType =
  | 'chat_message'
  | 'explanation'
  | 'search_answer'
  | 'knowledge_point'
  | 'upload_summary'
  | 'manual';

export const COLLECTION_SOURCE_TYPE_LABEL: Record<CollectionSourceType, string> = {
  chat_message: '对话消息',
  explanation: '讲解',
  search_answer: '搜题',
  knowledge_point: '知识点',
  upload_summary: '上传摘要',
  manual: '手动录入',
};

/**
 * 「渲染文本 ↔ 原文」对齐区间（契约 SnapshotSourceMapChunk），码点计。
 * 方案 C（Skyer 2026-11-03 拍板）：保存 markdown 快照时一次性算好存进 sourceMap，
 * 划选时查表换算，不实时算。
 */
export interface CollectionSourceMapChunk {
  /** 渲染文本（textContent）码点起点 */
  rs: number
  /** 渲染文本码点长度 */
  rl: number
  /** 原文码点起点 */
  ss: number
  /** 原文码点长度 */
  sl: number
  /** 仅 chunk 内含转义/字符引用时存在：[渲染 chunk 内偏移, 累计多消耗的源码点数]，升序 */
  jumps?: [number, number][]
}

export interface CollectionSourceMap {
  /** 映射格式版本，当前 1 */
  v: number
  chunks: CollectionSourceMapChunk[]
  /** 渲染文本总码点长（含块间合成换行，与 DOM textContent 同空间）；老映射可缺省 */
  total?: number
}

export interface CollectionSnapshot {
  content: string;
  format?: CollectionSnapshotFormat;
  /** 图片圈选场景：裁剪后小图的存储引用（第 805 行——原图不留存，只存坐标同样会变死图） */
  imageRef?: string | null;
  /** markdown 快照的渲染↔原文映射；plain 不需要（一一对应），老快照可能没有 */
  sourceMap?: CollectionSourceMap | null;
}

/** 来源引用，仅用于溯源标注，不承担内容可读性 */
export interface CollectionSourceRef {
  type?: CollectionSourceType;
  refId?: string | null;
  label?: string | null;
  subject?: Subject;
}

/** 划选高亮区间。偏移按 **Unicode 码点** 计、左闭右开——不是 JS 的 UTF-16 码元 */
export interface CollectionHighlight {
  start: number;
  end: number;
}

/** 「虚化」区间（#41）。口径同 CollectionHighlight；只改显示不改内容，故与「不可编辑」不冲突 */
export interface CollectionBlurState {
  start: number;
  end: number;
}

export interface CollectionItem {
  itemId: string;
  /** 自定义分组 ID；null = 未分组（内置维度不入表） */
  collectionId?: string | null;
  title?: string | null;
  snapshot: CollectionSnapshot;
  sourceRef?: CollectionSourceRef | null;
  highlights?: CollectionHighlight[];
  blurStates?: CollectionBlurState[];
  createdAt: string;
  /** 仅供展示「最近更新时间」，不要拿它判断覆盖，见文件头 */
  updatedAt?: string | null;
}

/** POST /me/collection/items 的响应 = 条目全字段 + created（契约 CollectionItemCreateResult） */
export interface CollectionItemCreateResult extends CollectionItem {
  /** true = 新建；false = 命中同一快照、覆盖既有条目（返回同一个 itemId） */
  created: boolean;
}

export interface CollectionItemCreate {
  snapshot: CollectionSnapshot;
  collectionId?: string | null;
  title?: string | null;
  sourceRef?: CollectionSourceRef | null;
}

/**
 * 标记更新。**没有 snapshot 字段**——内容不可编辑（第 821 行、D46）。
 * highlights / blurStates 是**全量覆盖**而非增量：一次提交当前全部区间。
 * collectionId 传 null = 移出分组；整个键不传 = 保持不变（后端按 model_fields_set 区分）。
 */
export interface CollectionItemUpdate {
  collectionId?: string | null;
  title?: string | null;
  highlights?: CollectionHighlight[];
  blurStates?: CollectionBlurState[];
}

/** 自定义分组（契约 Collection）。内置分组（学科/时间/掌握度）是筛选维度、不入表 */
export interface CollectionGroup {
  collectionId: string;
  name: string;
  itemCount?: number;
  createdAt: string;
  updatedAt?: string | null;
}

/** GET /me/collection —— 分组列表 */
export function fetchCollections(): Promise<{ items: CollectionGroup[] }> {
  return apiGet('/me/collection');
}

/** POST /me/collection —— 建自定义分组（内置分组名 400 / 重名 409） */
export function createCollection(name: string): Promise<CollectionGroup> {
  return apiPost('/me/collection', { name });
}

/** PATCH /me/collection/{collectionId} —— 重命名 */
export function renameCollection(collectionId: string, name: string): Promise<CollectionGroup> {
  return apiPatch(`/me/collection/${collectionId}`, { name });
}

/** DELETE /me/collection/{collectionId} —— 删分组；组内条目只解绑，不连带删除 */
export function deleteCollection(collectionId: string): Promise<void> {
  return apiDelete(`/me/collection/${collectionId}`);
}

/** GET /me/collection/items —— 条目列表，按时间倒序；collectionId 不传则返回全部 */
export function fetchCollectionItems(collectionId?: string): Promise<{ items: CollectionItem[] }> {
  return apiGet('/me/collection/items', { collectionId });
}

/** POST /me/collection/items —— 收藏；同一快照会覆盖，按返回的 created 决定提示文案 */
export function collectItem(payload: CollectionItemCreate): Promise<CollectionItemCreateResult> {
  return apiPost('/me/collection/items', payload);
}

/** GET /me/collection/items/{itemId} —— 单条 */
export function fetchCollectionItem(itemId: string): Promise<CollectionItem> {
  return apiGet(`/me/collection/items/${itemId}`);
}

/** PATCH /me/collection/items/{itemId} —— 改分组/标题/高亮/虚化 */
export function updateCollectionItem(
  itemId: string,
  payload: CollectionItemUpdate,
): Promise<CollectionItem> {
  return apiPatch(`/me/collection/items/${itemId}`, payload);
}

/** DELETE /me/collection/items/{itemId} —— 删除，幂等（重复删亦 204） */
export function deleteCollectionItem(itemId: string): Promise<void> {
  return apiDelete(`/me/collection/items/${itemId}`);
}

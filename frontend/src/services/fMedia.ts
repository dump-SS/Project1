/**
 * F 板块：题目图片的上传与取回（多模态拍题的最小入口）。
 *
 * 接口映射（docs/openapi.yaml，F 板块由 dev-3 在契约同步那轮补齐）：
 * - POST /f/media            上传（raw body，**不是** multipart/form-data）
 * - GET  /f/media/{key}      取回（二进制）
 *
 * ## 为什么不是 multipart
 *
 * `backend/pyproject.toml` 没有 `python-multipart`，写 `File(...)` / `UploadFile` 会让
 * FastAPI **启动直接报错**。后端因此收原始字节，这里用 `apiPostBinary` 原样发出。
 *
 * ## 引用块协议（§3.1）在本模块的体现
 *
 * F 提供两种引用块类型：`calculator` 与 `file_summary`。一条引用块 =
 * `{type, title, payload, display}`，与契约里的 `ChatCard` **完全同构**，所以：
 * - 上传产物通过 `toFileSummaryCard()` 适配成引用块，直接进对话上下文栈；
 * - `ChatCards` 对未知 type 有 title-only 兜底，**消费方不需要改 B 的任何代码**。
 *
 * @see docs/refactor-module-contracts.md §3.1
 */

import { apiGetBlob, apiPostBinary } from './http';

/** 与契约 ChatCard 同构的引用块（F 只用到其中两个 type）。 */
export interface FCard {
  type: string;
  title: string;
  payload?: Record<string, unknown>;
  display?: Record<string, unknown>;
}

/**
 * ⚠️ 类型归属说明：契约里已有 `ChatCard`（归 `types/api.ts` 管），此处刻意**不**重新定义
 * 全量的 ChatCard，只声明 F 侧用到的两个 type 的字面量联合，避免与契约脱钩后要改两处。
 */
export const F_CARD_TYPES = {
  CALCULATOR: 'calculator',
  FILE_SUMMARY: 'file_summary',
} as const;

export type FCardType = (typeof F_CARD_TYPES)[keyof typeof F_CARD_TYPES];

/** 上传回执（对应后端 MediaUploadResponse）。 */
export interface MediaUploadResult {
  mediaId: string;
  key: string;
  contentType: string;
  size: number;
  getUrl: string;
}

/** 允许上传的图片类型。**与后端 `_ALLOWED_IMAGE_TYPES` 一一对应**，改一边必须改另一边。 */
export const ACCEPTED_IMAGE_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
] as const;

/** 单文件大小上限，与后端 `MAX_UPLOAD_BYTES` 对齐（5MB）。 */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

/** 前端侧的类型/大小预检。**先在前端拦一道**能省掉一次无谓上传。 */
export function validateImageFile(file: File): string | null {
  if (!(ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type)) {
    return `只支持 ${ACCEPTED_IMAGE_TYPES.join(' / ')} 格式的图片`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `图片超过 ${MAX_UPLOAD_BYTES / (1024 * 1024)}MB 上限`;
  }
  return null;
}

/** 上传题目图片。失败直接抛 ApiError（由调用方决定要不要降级）。 */
export function uploadMedia(
  file: File,
  signal?: AbortSignal,
): Promise<MediaUploadResult> {
  const err = validateImageFile(file);
  if (err) return Promise.reject(new Error(err));
  return apiPostBinary<MediaUploadResult>('/f/media', file, file.type, signal);
}

/**
 * 取回图片字节。
 *
 * 返回 Blob 而不是字符串/图片地址：`<img>` 消费时用 `URL.createObjectURL(blob)`，
 * **调用方负责 revoke**，否则内存泄漏（见 `useMediaObjectUrl` 的用法说明）。
 */
export function fetchMedia(key: string, signal?: AbortSignal): Promise<Blob> {
  return apiGetBlob(`/f/media/${key}`, signal);
}

/**
 * 把一次上传的产物适配成 `file_summary` 引用块（§3.1）。
 *
 * payload 只放**显式输入输出**、不带隐式上下文（§3.1 的规则，对应 D51/#45）；
 * display 放渲染数据。图片本身**不进 payload**（只放 key，由取回接口按需取）——
 * 否则每次对话都会把整张图塞进模型上下文。
 */
export function toFileSummaryCard(
  result: MediaUploadResult,
  title = '题目图片',
): FCard {
  return {
    type: F_CARD_TYPES.FILE_SUMMARY,
    title,
    payload: {
      mediaKey: result.key,
      contentType: result.contentType,
      size: result.size,
    },
    display: {
      kind: 'image',
      mediaKey: result.key,
      getUrl: result.getUrl,
    },
  };
}

/** 从引用块取回图片的 key（渲染层用）。非 file_summary 返回 null。 */
export function mediaKeyOfCard(card: FCard): string | null {
  if (card.type !== F_CARD_TYPES.FILE_SUMMARY) return null;
  const key = (card.payload as { mediaKey?: unknown } | undefined)?.mediaKey;
  return typeof key === 'string' ? key : null;
}
/**
 * 带图 Chat 异步任务（openapi.yaml v1.13.0）—— 入队 + 轮询。
 *
 * 接口映射：
 * - POST /chat/media           入队，202 返回 jobId + **pollAfterMs**
 * - GET  /chat/jobs/{jobId}    轮询任务状态直到 done / failed
 *
 * ## 为什么要这个文件（而不是在组件里 fetch）
 *
 * 铁律 4：组件不直接 fetch，统一走 services/。此外本文件还承担两件组件不该管的事：
 * **轮询节奏**与**收尾**。
 *
 * ## 轮询间隔由服务端下发，不写死
 *
 * 契约在 202 响应里给 `pollAfterMs`（当前 2000ms）。写死间隔的问题是：带图延迟
 * 实测中位 105.7s、最大 245.8s（契约 v1.13.0 之前的生产实测），这个数以后还会变；
 * 一旦写死在前端，调节奏就得重新发布前端，而发版节奏不是我们能控的。
 * 所以这里**原样采用服务端给的间隔**，只在它缺失/非法时兜底到默认值。
 *
 * ## 停止条件（三条，缺一不可）
 *
 * 1. **终态**：拿到 `done` / `failed` 立刻停 —— 契约硬要求。
 * 2. **AbortSignal**：组件卸载时调用方 abort，停掉在途的 fetch 与下一次 setTimeout。
 *    少了这条，用户关页面后仍在后台打接口；更糟的是回调里 setState 会打到已卸载组件上。
 * 3. **总时长保险丝**：见 `MAX_POLL_MS`。契约上 job 一定会到终态（重启残留由
 *    启动对账置 failed），但前端不能假设后端永远正确 —— 无限轮询是把一个小故障
 *    变成"永远转圈"的最短路径，而"用户干等"恰是这次异步化要消灭的东西。
 */

import { apiGet, apiPost } from './http';
import type {
  ChatJob,
  ChatJobStatus,
  ChatMediaJobAccepted,
  ChatMediaJobRequest,
} from '@/types/api';

/** 服务端没给或给了个离谱的值时的兜底间隔（ms）。 */
const DEFAULT_POLL_AFTER_MS = 2000;

/**
 * 轮询总时长保险丝。
 *
 * 取 10 分钟：实测最坏 245.8s（约 4 分钟），10 分钟留了 2.5 倍余量。
 * 正常情况下**永远不会**触发——它是防「后端返回了非终态却一直不变」这种异常，
 * 触发时要让用户看到明确失败，而不是继续等。
 */
const MAX_POLL_MS = 10 * 60 * 1000;

/** 轮询被取消（组件卸载 / 主动中止）。调用方据此**不要**给用户弹错误。 */
export class ChatJobAbortedError extends Error {
  constructor() {
    super('chat job polling aborted');
    this.name = 'ChatJobAbortedError';
  }
}

/** 轮询超过保险丝仍未到终态。 */
export class ChatJobTimeoutError extends Error {
  constructor(jobId: string) {
    super(`chat job ${jobId} 轮询超时`);
    this.name = 'ChatJobTimeoutError';
  }
}

/** 任务是否已到终态（**终态必须停轮询**）。 */
export function isChatJobTerminal(status: ChatJobStatus | undefined): boolean {
  return status === 'done' || status === 'failed';
}

/** 入队一个带图 Chat 任务。202 只代表「已受理」，结果要靠轮询取。 */
export function sendMediaChat(
  body: ChatMediaJobRequest,
  signal?: AbortSignal,
): Promise<ChatMediaJobAccepted> {
  return apiPost<ChatMediaJobAccepted>('/chat/media', body, signal);
}

/** 拉一次任务状态。 */
export function getChatJob(jobId: string, signal?: AbortSignal): Promise<ChatJob> {
  return apiGet<ChatJob>(`/chat/jobs/${encodeURIComponent(jobId)}`, undefined, signal);
}

/** 可取消的等待。用 setTimeout 而非 setInterval：setInterval 会在请求慢于间隔时叠请求。 */
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ChatJobAbortedError());
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new ChatJobAbortedError());
    }
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * 轮询直到任务进入终态。
 *
 * @param pollAfterMs 服务端在 202 里下发的间隔；非法/缺失时用默认值兜底
 * @returns 终态的 job（done 或 failed）。**调用方要自己看 status**——
 *         失败是正常返回而不是抛异常，因为 failed 的 errorMessage 需要展示给用户。
 * @throws  {ChatJobAbortedError} 调用方 abort（组件卸载）时抛出
 * @throws  {ChatJobTimeoutError}  超过 MAX_POLL_MS 仍未到终态时抛出
 */
export async function pollChatJob(
  jobId: string,
  options: {
    pollAfterMs?: number;
    signal?: AbortSignal;
    /** 每次拿到非终态就回调一次，用于更新「处理中」UI。 */
    onUpdate?: (job: ChatJob) => void;
  } = {},
): Promise<ChatJob> {
  const { signal, onUpdate } = options;
  const hint = options.pollAfterMs;
  // 服务端给了就用；没给、给了 0/负数/NaN 才兜底。
  const intervalMs =
    typeof hint === 'number' && Number.isFinite(hint) && hint > 0
      ? hint
      : DEFAULT_POLL_AFTER_MS;

  const deadline = Date.now() + MAX_POLL_MS;

  // 先立刻查一次：任务可能在我们建立轮询前就已经完成（worker 很快的话）。
  for (;;) {
    if (signal?.aborted) throw new ChatJobAbortedError();

    const job = await getChatJob(jobId, signal);

    if (isChatJobTerminal(job.status)) return job;

    onUpdate?.(job);

    if (Date.now() >= deadline) throw new ChatJobTimeoutError(jobId);

    await sleep(intervalMs, signal);
  }
}

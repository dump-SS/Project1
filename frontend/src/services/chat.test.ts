/**
 * `pollChatJob` 三个停止分支的单测。
 *
 * ## 为什么只测这一个文件
 *
 * 前端此前零测试框架，而 `pollChatJob` 的三个停止分支是**纯逻辑**
 * （`setTimeout` + mock fetch + `AbortSignal`），不需要 DOM。
 * 因此这里刻意**只 mock `./http`**，不引 jsdom、不引 happy-dom。
 *
 * ## 覆盖的三条停止条件（对应 `services/chat.ts` 顶部注释）
 *
 * 1. **终态停**：`done` / `failed` 后**不再发起下一次请求**（契约硬要求）。
 * 2. **AbortSignal 中止**：abort 后立即停止，且抛 `ChatJobAbortedError`
 *    —— 调用方据此在 `finally` 里用 `if (!aborted)` 跳过 setState（`pages/Chat/index.tsx`）。
 * 3. **总时长保险丝**：一直停在 `processing` 时，到 `MAX_POLL_MS` 抛
 *    `ChatJobTimeoutError` 而不是永远转圈。**用 fake timers 测，不真等 10 分钟。**
 *
 * 另附两条实现自证（brief 的「顺带」项）：
 * `pollAfterMs` 非法值兜底 2000；用 `setTimeout` 而非 `setInterval`，请求未回来时不叠加。
 *
 * @see services/chat.ts
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatJob, ChatJobStatus } from '@/types/api';
import {
  ChatJobAbortedError,
  ChatJobTimeoutError,
  getChatJob,
  isChatJobTerminal,
  pollChatJob,
} from './chat';

// mock 掉 http 层：让分支逻辑与真实网络/响应解析解耦。
// 注意用可变引用，`vi.mock` 工厂会被提升，必须通过 vi.hoisted 暴露。
const http = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('./http', () => http);

/** 按 status 造一个最小可用的 ChatJob。 */
function job(status: ChatJobStatus, extra: Partial<ChatJob> = {}): ChatJob {
  return {
    jobId: 'job-1',
    status,
    createdAt: '2026-10-18T00:00:00Z',
    ...extra,
  };
}

const JOB_ID = 'job-1';

beforeEach(() => {
  http.apiGet.mockReset();
  http.apiPost.mockReset();
  // 默认给一个"永远 processing"的实现，各用例按需覆盖；
  // 这样忘记设实现的用例会立刻暴露成"意外成功/挂死"，而不是静默通过。
  http.apiGet.mockResolvedValue(job('processing'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('pollChatJob · 终态停', () => {
  it('拿到 done 就返回，且不再发起下一次请求', async () => {
    http.apiGet.mockResolvedValue(job('done', { reply: '答完了' }));

    const result = await pollChatJob(JOB_ID);

    expect(result.status).toBe('done');
    expect(result.reply).toBe('答完了');
    // 关键断言：终态后**只查过一次**。若实现漏了 return，会变成第二次查询。
    expect(http.apiGet).toHaveBeenCalledTimes(1);
  });

  it('拿到 failed 也是**正常返回**而不是抛异常（errorMessage 要能展示给用户）', async () => {
    http.apiGet.mockResolvedValue(
      job('failed', { errorCode: 'CHAT_JOB_INTERRUPTED', errorMessage: '实例重启了' }),
    );

    const result = await pollChatJob(JOB_ID);

    expect(result.status).toBe('failed');
    expect(result.errorMessage).toBe('实例重启了');
    expect(http.apiGet).toHaveBeenCalledTimes(1);
  });

  it('非终态时继续轮询，终态后停止：总请求数 = 非终态次数 + 1', async () => {
    http.apiGet
      .mockResolvedValueOnce(job('queued'))
      .mockResolvedValueOnce(job('processing'))
      .mockResolvedValueOnce(job('done'));

    const result = await pollChatJob(JOB_ID, { pollAfterMs: 1 });

    expect(result.status).toBe('done');
    expect(http.apiGet).toHaveBeenCalledTimes(3);
  });

  it('每次非终态都会回调 onUpdate，供「处理中」UI 更新', async () => {
    http.apiGet
      .mockResolvedValueOnce(job('queued'))
      .mockResolvedValueOnce(job('processing'))
      .mockResolvedValueOnce(job('done'));

    const onUpdate = vi.fn();
    await pollChatJob(JOB_ID, { pollAfterMs: 1, onUpdate });

    // 终态那一次**不**回调（已拿到结果，无需再更新"处理中"）
    expect(onUpdate).toHaveBeenCalledTimes(2);
    expect(onUpdate.mock.calls[0][0].status).toBe('queued');
    expect(onUpdate.mock.calls[1][0].status).toBe('processing');
  });

  it('isChatJobTerminal 只认 done / failed', () => {
    expect(isChatJobTerminal('done')).toBe(true);
    expect(isChatJobTerminal('failed')).toBe(true);
    expect(isChatJobTerminal('queued')).toBe(false);
    expect(isChatJobTerminal('processing')).toBe(false);
    expect(isChatJobTerminal(undefined)).toBe(false);
  });
});

describe('pollChatJob · AbortSignal 中止', () => {
  it('已 abort 时立即抛 ChatJobAbortedError，一次请求都不发', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(pollChatJob(JOB_ID, { signal: controller.signal })).rejects.toBeInstanceOf(
      ChatJobAbortedError,
    );
    expect(http.apiGet).not.toHaveBeenCalled();
  });

  it('轮询途中 abort：立即停止并抛 ChatJobAbortedError（不是超时）', async () => {
    const controller = new AbortController();
    http.apiGet.mockResolvedValueOnce(job('processing'));

    const pending = pollChatJob(JOB_ID, {
      pollAfterMs: 1000,
      signal: controller.signal,
    });

    // 等第一次查询落地、进入 sleep 之后再中止 —— 这才是"组件卸载"的真实时序。
    await vi.waitFor(() => expect(http.apiGet).toHaveBeenCalledTimes(1));
    controller.abort();

    await expect(pending).rejects.toBeInstanceOf(ChatJobAbortedError);
    // 终态/超时都不能发生：必须是 aborted 这一类
    await expect(pending).rejects.not.toBeInstanceOf(ChatJobTimeoutError);
  });

  it('abort 后 sleep 的定时器被清掉，不再发起下一次请求', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    http.apiGet.mockResolvedValueOnce(job('processing'));

    const pending = pollChatJob(JOB_ID, {
      pollAfterMs: 60_000,
      signal: controller.signal,
    });

    // 让第一次 fetch 的 await 结算，进入 sleep
    await vi.advanceTimersByTimeAsync(0);
    expect(http.apiGet).toHaveBeenCalledTimes(1);

    controller.abort();
    await expect(pending).rejects.toBeInstanceOf(ChatJobAbortedError);

    // 即使把时间推过原本的 60s 间隔，也不该有第二次请求
    await vi.advanceTimersByTimeAsync(120_000);
    expect(http.apiGet).toHaveBeenCalledTimes(1);
  });

  it('abort 错误带 name=ChatJobAbortedError，调用方可据此不弹错误提示', async () => {
    const controller = new AbortController();
    controller.abort();

    const err = await pollChatJob(JOB_ID, { signal: controller.signal }).catch((e) => e);

    expect(err).toBeInstanceOf(ChatJobAbortedError);
    expect(err.name).toBe('ChatJobAbortedError');
    // 与 ApiError 区分开：组件 catch 里靠 instanceof 分流
    expect(err.message).toContain('aborted');
  });
});

describe('pollChatJob · 10 分钟保险丝', () => {
  it('一直停在 processing 时到点抛 ChatJobTimeoutError，而不是永远转圈', async () => {
    vi.useFakeTimers();
    // beforeEach 的默认实现就是永远 processing，正好是这个用例要的
    const pending = pollChatJob(JOB_ID, { pollAfterMs: 2000 });

    const assertion = expect(pending).rejects.toBeInstanceOf(ChatJobTimeoutError);

    // MAX_POLL_MS = 10 * 60 * 1000；推到刚好越过保险丝
    await vi.advanceTimersByTimeAsync(10 * 60 * 1000 + 1);

    await assertion;
    // 到点即抛错：不该再补一次请求
    const callsAtTimeout = http.apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(http.apiGet).toHaveBeenCalledTimes(callsAtTimeout);
  });

  it('超时错误带上 jobId，便于排查是哪个任务卡住', async () => {
    vi.useFakeTimers();
    const pending = pollChatJob('job-stuck', { pollAfterMs: 2000 });
    const assertion = expect(pending).rejects.toThrow(/job-stuck/);

    await vi.advanceTimersByTimeAsync(10 * 60 * 1000 + 1);

    await assertion;
  });

  it('保险丝到点前若已到终态，则正常返回、不触发超时', async () => {
    vi.useFakeTimers();
    http.apiGet
      .mockResolvedValueOnce(job('processing'))
      .mockResolvedValueOnce(job('done', { reply: '刚好赶上' }));

    const pending = pollChatJob(JOB_ID, { pollAfterMs: 2000 });

    await vi.advanceTimersByTimeAsync(4000);

    await expect(pending).resolves.toMatchObject({ status: 'done', reply: '刚好赶上' });
  });
});

describe('pollChatJob · 轮询间隔（pollAfterMs）', () => {
  it('服务端给了合法间隔就原样采用，不写死', async () => {
    vi.useFakeTimers();
    http.apiGet
      .mockResolvedValueOnce(job('processing'))
      .mockResolvedValueOnce(job('done'));

    const pending = pollChatJob(JOB_ID, { pollAfterMs: 5000 });

    // 4999ms 时还没到第二次轮询
    await vi.advanceTimersByTimeAsync(4999);
    expect(http.apiGet).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(2);
    expect(http.apiGet).toHaveBeenCalledTimes(2);

    await expect(pending).resolves.toMatchObject({ status: 'done' });
  });

  it.each([
    ['缺失（undefined）', undefined],
    ['0', 0],
    ['负数', -1000],
    ['NaN', Number.NaN],
    ['Infinity', Number.POSITIVE_INFINITY],
  ])('非法值 %s 兜底到默认 2000ms', async (_label, hint) => {
    vi.useFakeTimers();
    http.apiGet
      .mockResolvedValueOnce(job('processing'))
      .mockResolvedValueOnce(job('done'));

    const pending = pollChatJob(JOB_ID, { pollAfterMs: hint as number | undefined });

    // 默认 2000：1999 时还没轮询第二次
    await vi.advanceTimersByTimeAsync(1999);
    expect(http.apiGet).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(2);
    expect(http.apiGet).toHaveBeenCalledTimes(2);

    await expect(pending).resolves.toMatchObject({ status: 'done' });
  });

  it('用 setTimeout 串行等待：上一次没回来时不会叠加下一次请求', async () => {
    vi.useFakeTimers();

    // 让第三次查询永远不结算，模拟"请求卡住"
    let callCount = 0;
    http.apiGet.mockImplementation(() => {
      callCount += 1;
      if (callCount === 3) return new Promise<ChatJob>(() => {});
      return Promise.resolve(job('processing'));
    });

    void pollChatJob(JOB_ID, { pollAfterMs: 1000 }).catch(() => {});

    // 连续推进远超 3 个间隔的时间
    await vi.advanceTimersByTimeAsync(1000 * 10);

    // 关键：若用的是 setInterval 且不 await 响应，请求会无限叠加；
    // 正确实现下总请求数应停在 3（第 3 次卡住不再前进）。
    expect(http.apiGet).toHaveBeenCalledTimes(3);
  });

  it('getChatJob 走 services 层而不是组件直接 fetch（铁律 4）', () => {
    expect(typeof getChatJob).toBe('function');
    expect(getChatJob('job-1')).toBeInstanceOf(Promise);
    expect(http.apiGet).toHaveBeenCalledWith(
      `/chat/jobs/${encodeURIComponent(JOB_ID)}`,
      undefined,
      undefined,
    );
  });
});

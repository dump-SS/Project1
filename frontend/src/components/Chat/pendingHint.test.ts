/**
 * 纯文本「在等」提示的单测。
 *
 * ## 为什么单独测这个模块
 *
 * `pendingHint` 的计时与文案升级是**纯逻辑**（两个 `setTimeout`），不需要 DOM。
 * 放在 `components/Chat/pendingHint.ts` 而不是塞进页面组件里，就是为了让这部分
 * 能在 node 环境下被真正测到 —— 前端现在有 vitest 了，就别把能测的逻辑藏进组件。
 *
 * 覆盖：
 * - 两档阈值与升级顺序（15s 第一档、45s 第二档）
 * - **短问答不打扰**：取消后不再触发
 * - 文案口径：不含禁用词、不含无信息量的套话
 *
 * @see components/Chat/pendingHint.ts
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  startTextPendingHint,
  TEXT_HINT,
  TEXT_HINT_DELAY_MS,
  TEXT_HINT_SLOW,
  TEXT_HINT_SLOW_DELAY_MS,
} from './pendingHint';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('pendingHint · 阈值与升级顺序', () => {
  it('15 秒内不出提示（短问答不该被打扰）', () => {
    const onHint = vi.fn();
    startTextPendingHint(onHint);

    vi.advanceTimersByTime(TEXT_HINT_DELAY_MS - 1);
    expect(onHint).not.toHaveBeenCalled();
  });

  it('到 15 秒出第一档文案', () => {
    const onHint = vi.fn();
    startTextPendingHint(onHint);

    vi.advanceTimersByTime(TEXT_HINT_DELAY_MS);
    expect(onHint).toHaveBeenCalledTimes(1);
    expect(onHint).toHaveBeenCalledWith(TEXT_HINT);
  });

  it('到 45 秒升级为第二档文案', () => {
    const onHint = vi.fn();
    startTextPendingHint(onHint);

    vi.advanceTimersByTime(TEXT_HINT_SLOW_DELAY_MS);
    expect(onHint).toHaveBeenCalledTimes(2);
    expect(onHint).toHaveBeenNthCalledWith(1, TEXT_HINT);
    expect(onHint).toHaveBeenNthCalledWith(2, TEXT_HINT_SLOW);
  });

  it('两档阈值本身是 15s / 45s（改动需同步改测试与理由）', () => {
    expect(TEXT_HINT_DELAY_MS).toBe(15_000);
    expect(TEXT_HINT_SLOW_DELAY_MS).toBe(45_000);
    // 第二档必须晚于第一档，否则会出现「先升级后降级」
    expect(TEXT_HINT_SLOW_DELAY_MS).toBeGreaterThan(TEXT_HINT_DELAY_MS);
  });
});

describe('pendingHint · 取消后不再提示', () => {
  it('取消后第一档不再触发（秒级问答不受打扰）', () => {
    const onHint = vi.fn();
    const stop = startTextPendingHint(onHint);

    vi.advanceTimersByTime(TEXT_HINT_DELAY_MS - 1000);
    stop();
    vi.advanceTimersByTime(10_000);

    expect(onHint).not.toHaveBeenCalled();
  });

  it('取消后连第二档也不再触发（响应已到就不该再弹「在等」）', () => {
    const onHint = vi.fn();
    const stop = startTextPendingHint(onHint);

    vi.advanceTimersByTime(TEXT_HINT_DELAY_MS + 1000);
    expect(onHint).toHaveBeenCalledTimes(1);

    stop();
    vi.advanceTimersByTime(60_000);

    // 只有第一档那次，没有第二档
    expect(onHint).toHaveBeenCalledTimes(1);
  });

  it('取消是幂等的：调两次不报错、不重复触发', () => {
    const onHint = vi.fn();
    const stop = startTextPendingHint(onHint);

    expect(() => {
      stop();
      stop();
    }).not.toThrow();

    vi.advanceTimersByTime(120_000);
    expect(onHint).not.toHaveBeenCalled();
  });

  it('取消后立刻再发一条，旧定时器不会污染新请求', () => {
    const first = vi.fn();
    const stopFirst = startTextPendingHint(first);
    stopFirst();

    const second = vi.fn();
    startTextPendingHint(second);

    vi.advanceTimersByTime(TEXT_HINT_DELAY_MS);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});

describe('pendingHint · 文案口径', () => {
  it('两档文案都不为空、互不相同', () => {
    expect(TEXT_HINT.trim().length).toBeGreaterThan(0);
    expect(TEXT_HINT_SLOW.trim().length).toBeGreaterThan(0);
    expect(TEXT_HINT).not.toBe(TEXT_HINT_SLOW);
  });

  it('不含 visual-language §6.1 的禁用词', () => {
    // 禁用词表：冲刺、升级、你真棒、超越自己、满血复活、提升自我、优先时代、惊人、落后、太少
    const banned = ['冲刺', '升级', '你真棒', '超越自己', '满血复活', '提升自我', '优先时代', '惊人', '落后', '太少'];
    for (const word of banned) {
      expect(TEXT_HINT).not.toContain(word);
      expect(TEXT_HINT_SLOW).not.toContain(word);
    }
  });

  it('不用「请稍候」这类无信息量的套话', () => {
    for (const word of ['请稍候', '请稍等', '稍等', '马上好', '正在努力', '加油']) {
      expect(TEXT_HINT).not.toContain(word);
      expect(TEXT_HINT_SLOW).not.toContain(word);
    }
  });

  it('不外泄内部术语（§6.2：画像/归因等纯内部分析维度不进用户文案）', () => {
    for (const word of ['画像', '归因', '状态画像', 'tokens', 'usage_ledger']) {
      expect(TEXT_HINT).not.toContain(word);
      expect(TEXT_HINT_SLOW).not.toContain(word);
    }
  });

  it('说清「在生成」这件事（两档都含状态描述）', () => {
    expect(TEXT_HINT).toContain('生成');
    expect(TEXT_HINT_SLOW).toContain('生成');
  });
});

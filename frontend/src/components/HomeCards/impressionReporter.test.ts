/**
 * IntersectionObserver 上报判定单测（纯函数，node 环境）。
 *
 * 钉死 charter §四 两条硬要求：
 * - 卡片**真正进入视口**才报 shown（isIntersecting 且 ratio>0；擦边 0 不算）；
 * - 同一张卡反复进视口**不重复报**。
 */
import { describe, expect, it, vi } from 'vitest';
import { createShownReporter, type ShownEntryLike } from './impressionReporter';

const entry = (key: string, isIntersecting: boolean, ratio: number): ShownEntryLike => ({
  isIntersecting,
  intersectionRatio: ratio,
  target: { dataset: { impressionKey: key } },
});

describe('createShownReporter', () => {
  it('未进视口 / 比例为 0 都不报', () => {
    const report = vi.fn();
    const seen = new Set<string>();
    const reporter = createShownReporter((k) => seen.has(k), (k) => seen.add(k), report);
    reporter([entry('go_on:fp1', false, 0), entry('go_on:fp2', true, 0)]);
    expect(report).not.toHaveBeenCalled();
  });

  it('真正进视口才报，且只报一次（反复进视口去重）', () => {
    const report = vi.fn();
    const seen = new Set<string>();
    const reporter = createShownReporter((k) => seen.has(k), (k) => seen.add(k), report);
    reporter([entry('go_on:fp1', true, 0.6)]);
    reporter([entry('go_on:fp1', false, 0)]);
    reporter([entry('go_on:fp1', true, 1)]);
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith('go_on:fp1');
  });

  it('不同指纹各自报一次', () => {
    const report = vi.fn();
    const seen = new Set<string>();
    const reporter = createShownReporter((k) => seen.has(k), (k) => seen.add(k), report);
    reporter([entry('go_on:fp1', true, 0.5), entry('recommend:fp2', true, 0.5)]);
    expect(report).toHaveBeenCalledTimes(2);
  });

  it('没有 impressionKey 的 entry 忽略（不炸不报）', () => {
    const report = vi.fn();
    const seen = new Set<string>();
    const reporter = createShownReporter((k) => seen.has(k), (k) => seen.add(k), report);
    reporter([{ isIntersecting: true, intersectionRatio: 1, target: null }]);
    expect(report).not.toHaveBeenCalled();
  });
});

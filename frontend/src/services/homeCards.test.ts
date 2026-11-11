/**
 * homeCards service 的请求形状单测（node 环境，只 mock ./http，不引 jsdom）。
 *
 * 钉死两条易错口径：
 * - GET /me/home-cards 返回数组（不是 {groups} 包装），service 原样透传；
 * - POST /me/card-impressions 请求体 camelCase（cardType 而非 card_type），shownAt 可省略。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./http', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiPost } from './http';
import { getHomeCards, reportCardImpression } from './homeCards';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getHomeCards', () => {
  it('走 apiGet /me/home-cards，数组原样透传', async () => {
    const groups = [{ group: 'go_on', cards: [] }];
    vi.mocked(apiGet).mockResolvedValue(groups as never);
    const res = await getHomeCards();
    expect(apiGet).toHaveBeenCalledWith('/me/home-cards', undefined, undefined);
    expect(res).toBe(groups);
  });
});

describe('reportCardImpression', () => {
  it('请求体 camelCase：group/cardType/fingerprint/action，不含 card_type', async () => {
    vi.mocked(apiPost).mockResolvedValue({ id: 'ci_1', createdAt: '2026-11-11T00:00:00Z' } as never);
    await reportCardImpression({
      group: 'go_on',
      cardType: 'continue_plan',
      fingerprint: 'go_on:plan:p1',
      action: 'dismissed',
    });
    expect(apiPost).toHaveBeenCalledTimes(1);
    const [path, body] = vi.mocked(apiPost).mock.calls[0];
    expect(path).toBe('/me/card-impressions');
    expect(body).toEqual({
      group: 'go_on',
      cardType: 'continue_plan',
      fingerprint: 'go_on:plan:p1',
      action: 'dismissed',
    });
    expect(body).not.toHaveProperty('card_type');
    expect(body).not.toHaveProperty('shownAt');
  });

  it('shownAt 传了就带上（服务端 otherwise 记请求时刻）', async () => {
    vi.mocked(apiPost).mockResolvedValue({} as never);
    await reportCardImpression({
      group: 'insight',
      cardType: 'group_insight',
      fingerprint: 'insight:junior:fatigue:2026-W46',
      action: 'shown',
      shownAt: '2026-11-11T00:00:00Z',
    });
    const [, body] = vi.mocked(apiPost).mock.calls[0];
    expect(body).toHaveProperty('shownAt', '2026-11-11T00:00:00Z');
  });
});

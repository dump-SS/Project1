/**
 * 三组卡区展示层渲染单测：renderToStaticMarkup，node 环境不需要 jsdom。
 * （IntersectionObserver 在 useEffect 里，server render 不跑 effect，正好只验结构。）
 *
 * 钉死：组顺序按传入顺序、组标题、type 文字标签、划掉按钮、空态有可点击对话起点。
 */
import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import HomeCardGroups, { EMPTY_STARTERS } from './HomeCardGroups';
import type { HomeCardGroupResult } from '@/services/homeCards';

const groups: HomeCardGroupResult[] = [
  {
    group: 'go_on',
    cards: [
      {
        type: 'continue_plan',
        display: { title: '继续 11-11 计划 · 完成 2/6', subtitle: '下一项：函数单调性' },
        fingerprint: 'go_on:plan:p1',
      },
    ],
  },
  {
    group: 'insight',
    cards: [
      {
        type: 'group_insight',
        display: { title: '同节奏人群本周疲劳度有变化 · 25 名匿名同龄人' },
        fingerprint: 'insight:junior:fatigue:2026-W46',
      },
    ],
  },
];

const noop = () => {};
const reporter = () => {};

describe('HomeCardGroups 渲染', () => {
  it('组顺序与组标题按传入顺序（Go on 在洞察前）', () => {
    const html = renderToStaticMarkup(
      <HomeCardGroups groups={groups} reporter={reporter} onCardClick={noop} onDismiss={noop} onStarter={noop} />,
    );
    expect(html.indexOf('Go on')).toBeGreaterThan(-1);
    expect(html.indexOf('Go on')).toBeLessThan(html.indexOf('洞察'));
    expect(html).toContain('继续 11-11 计划 · 完成 2/6');
    expect(html).toContain('下一项：函数单调性');
  });

  it('type 用文字标签区分（#51 未拍板前的结构版）', () => {
    const html = renderToStaticMarkup(
      <HomeCardGroups groups={groups} reporter={reporter} onCardClick={noop} onDismiss={noop} onStarter={noop} />,
    );
    expect(html).toContain('继续计划');
    expect(html).toContain('群体洞察');
  });

  it('每张卡有划掉按钮与 impression key（供 IO 上报）', () => {
    const html = renderToStaticMarkup(
      <HomeCardGroups groups={groups} reporter={reporter} onCardClick={noop} onDismiss={noop} onStarter={noop} />,
    );
    expect(html).toContain('data-impression-key="go_on:go_on:plan:p1"');
    expect(html).toContain('划掉');
  });

  it('空态给可点击对话起点', () => {
    const onStarter = vi.fn();
    const html = renderToStaticMarkup(
      <HomeCardGroups groups={[]} reporter={reporter} onCardClick={noop} onDismiss={noop} onStarter={onStarter} />,
    );
    expect(html).toContain('今天还没有推荐卡');
    for (const s of EMPTY_STARTERS) expect(html).toContain(s);
  });
});

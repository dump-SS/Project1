/**
 * 收藏快照标记（高亮 / 虚化）的区间运算单测。
 *
 * ## 为什么这部分必须单独测
 *
 * 契约要求偏移**按 Unicode 码点计**（docs/openapi.yaml 的 CollectionHighlight /
 * CollectionBlurState），而 JS 的字符串下标是 **UTF-16 码元**——emoji 与扩展区汉字
 * 占两个码元。这类错位在界面上表现为「虚化标错了位置」，肉眼很难归因，
 * 所以把区间运算从组件里抽成纯函数，在 node 环境下真测（不引 jsdom）。
 *
 * 覆盖：
 * - 码点计数与 UTF-16 下标互转（含 emoji / 扩展 B 区汉字）
 * - normalizeRanges 的夹取、丢弃空区间、排序、重叠合并
 * - splitByMarks 的分段正确性 + **虚化优先于高亮** + 分段可无损拼回原文
 * - blurAll（§4.8.4 第 826 行「全部虚化」一键）
 * - addRange / removeRange 的**全量覆盖**语义（契约规定 PATCH 提交全量而非增量）
 *
 * @see pages/Collection/snapshotMarks.ts
 */
import { describe, expect, it } from 'vitest';
import {
  addRange,
  blurAll,
  countCodepoints,
  normalizeRanges,
  removeRange,
  splitByMarks,
  utf16IndexToCodepoint,
} from './snapshotMarks';

describe('countCodepoints / utf16IndexToCodepoint', () => {
  it('ASCII 与中日韩文字：码点数等于 length', () => {
    expect(countCodepoints('abc')).toBe(3);
    expect(countCodepoints('黑洞不发光')).toBe(5);
  });

  it('emoji 占两个 UTF-16 码元，但只算一个码点', () => {
    expect('😀'.length).toBe(2);
    expect(countCodepoints('😀')).toBe(1);
    expect(countCodepoints('a😀b')).toBe(3);
  });

  it('扩展 B 区汉字（U+20000）同样是代理对', () => {
    expect('𠀀'.length).toBe(2);
    expect(countCodepoints('𠀀')).toBe(1);
  });

  it('UTF-16 下标转码点偏移：代理对之后的下标要减掉多出来的码元', () => {
    const text = 'a😀b';
    // 'a😀b' 的 UTF-16 下标：a=0、😀=1..2、b=3
    expect(utf16IndexToCodepoint(text, 0)).toBe(0);
    expect(utf16IndexToCodepoint(text, 1)).toBe(1);
    expect(utf16IndexToCodepoint(text, 3)).toBe(2);
    expect(utf16IndexToCodepoint(text, text.length)).toBe(3);
  });
});

describe('normalizeRanges', () => {
  it('丢弃空区间与反向区间', () => {
    expect(normalizeRanges([{ start: 3, end: 3 }], 10)).toEqual([]);
    expect(normalizeRanges([{ start: 5, end: 2 }], 10)).toEqual([]);
  });

  it('夹取到 [0, length]', () => {
    expect(normalizeRanges([{ start: -4, end: 99 }], 10)).toEqual([{ start: 0, end: 10 }]);
  });

  it('排序后合并重叠与首尾相接的区间', () => {
    expect(
      normalizeRanges(
        [
          { start: 6, end: 9 },
          { start: 0, end: 3 },
          { start: 3, end: 5 },
        ],
        10,
      ),
    ).toEqual([
      { start: 0, end: 5 },
      { start: 6, end: 9 },
    ]);
  });

  it('被包含的区间不会撑大外层', () => {
    expect(
      normalizeRanges(
        [
          { start: 0, end: 10 },
          { start: 2, end: 4 },
        ],
        10,
      ),
    ).toEqual([{ start: 0, end: 10 }]);
  });

  it('null / undefined 当空数组', () => {
    expect(normalizeRanges(null, 10)).toEqual([]);
    expect(normalizeRanges(undefined, 10)).toEqual([]);
  });
});

describe('splitByMarks', () => {
  const content = '黑洞是时空的一个区域';

  it('没有任何标记时整篇是一个 plain 段', () => {
    expect(splitByMarks(content, [], [])).toEqual([
      { text: content, kind: 'plain', start: 0 },
    ]);
  });

  it('按码点切段，分段可无损拼回原文', () => {
    const segments = splitByMarks(content, [], [{ start: 2, end: 5 }]);
    expect(segments.map((s) => s.text).join('')).toBe(content);
    expect(segments.map((s) => s.kind)).toEqual(['plain', 'blur', 'plain']);
    expect(segments[1].text).toBe('是时空');
    expect(segments[1].start).toBe(2);
  });

  it('虚化优先于高亮：重叠处按 blur 渲染', () => {
    const segments = splitByMarks('abcdef', [{ start: 0, end: 4 }], [{ start: 2, end: 6 }]);
    expect(segments.map((s) => [s.start, s.kind])).toEqual([
      [0, 'highlight'],
      [2, 'blur'],
    ]);
  });

  it('高亮与虚化互不重叠时各自成段', () => {
    const segments = splitByMarks('abcdef', [{ start: 0, end: 2 }], [{ start: 4, end: 6 }]);
    expect(segments.map((s) => s.kind)).toEqual(['highlight', 'plain', 'blur']);
  });

  it('emoji 不会把区间算错位', () => {
    const text = 'a😀b😀c';
    // 码点：a=0 😀=1 b=2 😀=3 c=4，共 5 个
    expect(countCodepoints(text)).toBe(5);
    const segments = splitByMarks(text, [], [{ start: 1, end: 4 }]);
    expect(segments.map((s) => s.text).join('')).toBe(text);
    expect(segments[1]).toEqual({ text: '😀b😀', kind: 'blur', start: 1 });
  });

  it('越界区间被夹取，不产生空段', () => {
    const segments = splitByMarks('abc', null, [{ start: 1, end: 99 }]);
    expect(segments).toEqual([
      { text: 'a', kind: 'plain', start: 0 },
      { text: 'bc', kind: 'blur', start: 1 },
    ]);
  });
});

describe('blurAll / addRange / removeRange', () => {
  it('blurAll 把整篇作为一个区间；空内容返回空数组', () => {
    expect(blurAll('abc')).toEqual([{ start: 0, end: 3 }]);
    expect(blurAll('')).toEqual([]);
  });

  it('addRange 返回全量区间并合并重叠（契约要求 PATCH 全量覆盖）', () => {
    expect(addRange([{ start: 0, end: 3 }], { start: 2, end: 6 }, 10)).toEqual([
      { start: 0, end: 6 },
    ]);
    expect(addRange([], { start: 1, end: 2 }, 10)).toEqual([{ start: 1, end: 2 }]);
  });

  it('removeRange 只裁掉目标区间，中间挖空时一段变两段', () => {
    expect(removeRange([{ start: 0, end: 10 }], { start: 3, end: 5 }, 10)).toEqual([
      { start: 0, end: 3 },
      { start: 5, end: 10 },
    ]);
  });

  it('removeRange 对不相交的区间无影响', () => {
    expect(removeRange([{ start: 0, end: 2 }], { start: 5, end: 7 }, 10)).toEqual([
      { start: 0, end: 2 },
    ]);
  });
});

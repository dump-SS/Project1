/**
 * markdown「渲染文本 ↔ 原文」映射的单测（方案 C 的核心正确性）。
 *
 * ## 为什么必须单测
 *
 * 高亮/虚化区间按契约落在**原文**上，而划选发生在**渲染后的 DOM** 上。
 * 映射错一个码点，界面上就是「虚化标错位置」，且极难肉眼归因。
 * 本文件不引 jsdom：映射是纯函数（markdown 字符串进、区间换算出），node 环境即可真测。
 *
 * ## 渲染空间的口径（真跑 + hast dump 双重坐实）
 *
 * 渲染空间 = react-markdown 输出的 textContent，它**包含块级兄弟之间的合成换行**
 * （mdast-util-to-hast 插的 pos=NONE 文本节点，表格/列表/硬换行里也有）。
 * 所以下面的渲染偏移是「含换行间隙」的：标题 0-3、间隙、正文段 4 起……
 * 这些常数按 `remark-rehype` 的 hast dump 手算，并在浏览器里用
 * host.textContent.indexOf 复核过（见交付说明）。
 *
 * 覆盖：
 * - 总长 = 游标终值（含间隙），不是 chunk 长度和
 * - 加粗/斜体/列表/表格/链接/行内码/代码块：chunk 边界与原文偏移精确
 * - 转义 `\*` 与字符引用 `&amp;`：jumps 精确到字符（选到被转义字符本身也指对，且连语法字符一起盖住）
 * - 跨 chunk 选区、含语法字符的源区间（全部虚化的 0..全文长）、端点反了
 * - source → rendered → source 往返不变
 *
 * @see utils/markdownSourceMap.ts
 */
import { describe, expect, it } from 'vitest';
import { buildSourceMap, renderedLength, renderedRangeToSource, sourceRangeToRendered } from './markdownSourceMap';

const SRC = `# 标题一

正文 **加粗** 与 *斜体*，转义 \\* 星号，实体 &amp; 符号。

- 列表项一
- 列表项二含 \`行内码\`

\`\`\`python
print("块级码")
\`\`\`

[链接文字](https://example.com) 与 ![图alt](https://x/y.png)

| 甲 | 乙 |
|---|---|
| 1 | 2 |

换行前  
换行后（硬换行）
`;

const { map, approxChunks } = buildSourceMap(SRC);
const toSource = (rs: number, re: number) => renderedRangeToSource(rs, re, map);
const srcRangeOf = (text: string) => {
  const at = SRC.indexOf(text);
  return { start: at, end: at + [...text].length };
};

describe('buildSourceMap 总览', () => {
  it('渲染总长含块间合成换行（hast dump 手算 101）', () => {
    expect(map.total).toBe(101);
    expect(renderedLength(map)).toBe(101);
  });

  it('整篇无近似 chunk（全精确）', () => {
    expect(approxChunks).toBe(0);
  });
});

describe('renderedRangeToSource 精确性', () => {
  it('加粗文字：渲染 7-9 → 原文去掉 ** 的位置', () => {
    expect(toSource(7, 9)).toEqual(srcRangeOf('加粗'));
  });

  it('斜体文字', () => {
    expect(toSource(12, 14)).toEqual(srcRangeOf('斜体'));
  });

  it('被转义的星号：连反斜杠一起盖住（否则切原文渲染会漏出一个反斜杠残影）', () => {
    const bs = SRC.indexOf('\\*');
    expect(toSource(18, 19)).toEqual({ start: bs, end: bs + 2 });
  });

  it('实体解码后的 &：连 &amp; 五个源字符一起盖住', () => {
    const amp = SRC.indexOf('&amp;');
    expect(toSource(26, 27)).toEqual({ start: amp, end: amp + 5 });
  });

  it('实体之后的字符不被带偏：渲染 27-28（空格）→ 原文分号后的空格', () => {
    const after = SRC.indexOf('&amp;') + 5;
    expect(toSource(27, 28)).toEqual({ start: after, end: after + 1 });
  });

  it('行内码：剥掉反引号后精确', () => {
    expect(toSource(44, 47)).toEqual(srcRangeOf('行内码'));
  });

  it('代码块：剥掉围栏后精确（含值里的尾换行）', () => {
    expect(toSource(49, 62)).toEqual(srcRangeOf('print("块级码")\n'));
  });

  it('表格单元格', () => {
    const yi = SRC.indexOf('乙');
    expect(toSource(76, 77)).toEqual({ start: yi, end: yi + 1 });
  });

  it('链接只映射文字部分，URL 不在渲染文本里', () => {
    expect(toSource(63, 67)).toEqual(srcRangeOf('链接文字'));
  });

  it('跨 chunk 选区：两端各自换算（中间语法字符自然落入原文区间）', () => {
    expect(toSource(4, 14)).toEqual({
      start: SRC.indexOf('正文'),
      end: SRC.indexOf('斜体') + 2,
    });
  });

  it('硬换行：br 不占渲染文本，但块间合成换行占', () => {
    expect(toSource(89, 92)).toEqual(srcRangeOf('换行前'));
    expect(toSource(93, 101)).toEqual(srcRangeOf('换行后（硬换行）'));
  });
});

describe('source → rendered → source 往返', () => {
  it('加粗/行内码/代码块/链接：原文换到渲染再换回来不变', () => {
    for (const text of ['加粗', '行内码', 'print("块级码")', '链接文字']) {
      const src = srcRangeOf(text);
      const rendered = sourceRangeToRendered(src.start, src.end, map);
      expect(renderedRangeToSource(rendered.start, rendered.end, map)).toEqual(src);
    }
  });

  it('加粗的原文区间换到渲染就是 7-9（渲染文本里 ** 不占位）', () => {
    const src = srcRangeOf('加粗');
    expect(sourceRangeToRendered(src.start, src.end, map)).toEqual({ start: 7, end: 9 });
  });

  it('含语法字符的源区间（「全部虚化」存的 0..全文长）落回渲染全文', () => {
    expect(sourceRangeToRendered(0, SRC.length, map)).toEqual({
      start: 0,
      end: renderedLength(map),
    });
  });

  it('源区间盖住 ** 时收敛到它包住的渲染文字，不会跑到文末', () => {
    const src = srcRangeOf('加粗');
    expect(sourceRangeToRendered(src.start - 2, src.end + 2, map)).toEqual({ start: 7, end: 9 });
  });
});

describe('退化与边界', () => {
  it('无语法纯文本：单 chunk 1:1', () => {
    const r = buildSourceMap('就是普通一句话，没有语法。');
    expect(r.approxChunks).toBe(0);
    expect(r.map.chunks).toHaveLength(1);
    expect(renderedRangeToSource(2, 6, r.map)).toEqual({ start: 2, end: 6 });
  });

  it('空字符串：零 chunk，换算不抛错', () => {
    const r = buildSourceMap('');
    expect(r.map.chunks).toHaveLength(0);
    expect(renderedRangeToSource(0, 0, r.map)).toEqual({ start: 0, end: 0 });
  });

  it('选区端点反了会自动纠正', () => {
    expect(toSource(9, 7)).toEqual(srcRangeOf('加粗'));
  });
});

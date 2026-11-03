/**
 * 收藏快照的标记（高亮 / 虚化）区间运算 —— 纯函数，无 DOM 依赖，可直接单测。
 *
 * 口径来自契约 docs/openapi.yaml：CollectionHighlight / CollectionBlurState 的 start、end
 * **按 Unicode 码点计、左闭右开**（lead-1 2026-11-02 拍板：区间落在原文 markdown 源文本上，
 * 不是渲染后的可见文本）。
 *
 * ⚠️ JS 的字符串下标与 String.slice 都是 **UTF-16 码元**，含 emoji 或扩展区汉字时与码点不一致，
 * 所以这里一律先 Array.from(content) 拆成码点再算，绝不直接用 slice 的下标当偏移。
 */

export interface MarkRange {
  start: number
  end: number
}

export type MarkKind = 'plain' | 'highlight' | 'blur'

export interface MarkSegment {
  text: string
  kind: MarkKind
  /** 该段起点在原文中的码点偏移 */
  start: number
}

/** 码点数（不是 length：length 数的是 UTF-16 码元） */
export function countCodepoints(text: string): number {
  return Array.from(text).length
}

/** UTF-16 下标 → 码点偏移 */
export function utf16IndexToCodepoint(text: string, index: number): number {
  return countCodepoints(text.slice(0, index))
}

/**
 * 规整区间：丢掉非法/空区间、按 start 排序、夹到 [0, length]、重叠的合并。
 *
 * 合并是必须的：契约定 highlights / blurStates 是**全量覆盖**提交，
 * 用户反复划选会产生大量重叠碎片，不合并会让渲染分段数无上限增长。
 */
export function normalizeRanges(ranges: MarkRange[] | null | undefined, length: number): MarkRange[] {
  const valid = (ranges ?? [])
    .map((r) => ({
      start: Math.max(0, Math.min(length, Math.trunc(r.start))),
      end: Math.max(0, Math.min(length, Math.trunc(r.end))),
    }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start || a.end - b.end)

  const merged: MarkRange[] = []
  for (const r of valid) {
    const last = merged[merged.length - 1]
    if (last && r.start <= last.end) {
      last.end = Math.max(last.end, r.end)
    } else {
      merged.push({ ...r })
    }
  }
  return merged
}

/**
 * 按标记把原文切成渲染段。
 *
 * 重叠时**虚化优先于高亮**：虚化的用途之一是「隐藏自己不想看到的信息」（§4.8.4 第 824 行），
 * 被虚化盖住的高亮没有意义，让虚化赢才不会出现"标了高亮反而露出内容"。
 */
export function splitByMarks(
  content: string,
  highlights: MarkRange[] | null | undefined,
  blurs: MarkRange[] | null | undefined,
): MarkSegment[] {
  const codepoints = Array.from(content)
  const length = codepoints.length
  const hl = normalizeRanges(highlights, length)
  const bl = normalizeRanges(blurs, length)

  const bounds = new Set<number>([0, length])
  for (const r of [...hl, ...bl]) {
    bounds.add(r.start)
    bounds.add(r.end)
  }
  const cuts = [...bounds].sort((a, b) => a - b)

  const inRange = (ranges: MarkRange[], at: number, before: number) =>
    ranges.some((r) => r.start <= at && before <= r.end)

  const segments: MarkSegment[] = []
  for (let i = 0; i < cuts.length - 1; i += 1) {
    const start = cuts[i]
    const end = cuts[i + 1]
    if (end <= start) continue
    const kind: MarkKind = inRange(bl, start, end)
      ? 'blur'
      : inRange(hl, start, end)
        ? 'highlight'
        : 'plain'
    segments.push({ text: codepoints.slice(start, end).join(''), kind, start })
  }

  // 相邻同类型段合并：切分点来自两套区间的边界，一段连续的虚化可能被高亮边界切成几截。
  // 不合并的话 filter: blur 会按元素分别应用，接缝处出现视觉断层。
  const merged: MarkSegment[] = []
  for (const seg of segments) {
    const last = merged[merged.length - 1]
    if (last && last.kind === seg.kind) {
      last.text += seg.text
    } else {
      merged.push({ ...seg })
    }
  }
  return merged
}

/** 「全部虚化」一键（§4.8.4 第 826 行）：整篇作为一个虚化区间 */
export function blurAll(content: string): MarkRange[] {
  const length = countCodepoints(content)
  return length > 0 ? [{ start: 0, end: length }] : []
}

/**
 * 把用户新划选的一段并进去，返回**全量**区间（契约要求 PATCH 全量覆盖，不是增量）。
 * 与既有区间重叠时合并，等价于「把这一段也标记上」。
 */
export function addRange(
  existing: MarkRange[] | null | undefined,
  next: MarkRange,
  length: number,
): MarkRange[] {
  return normalizeRanges([...(existing ?? []), next], length)
}

/** 取消某一段标记：与之重叠的既有区间会被裁掉（可能一段变两段） */
export function removeRange(
  existing: MarkRange[] | null | undefined,
  target: MarkRange,
  length: number,
): MarkRange[] {
  const out: MarkRange[] = []
  for (const r of normalizeRanges(existing, length)) {
    if (r.end <= target.start || r.start >= target.end) {
      out.push(r)
      continue
    }
    if (r.start < target.start) out.push({ start: r.start, end: target.start })
    if (r.end > target.end) out.push({ start: target.end, end: r.end })
  }
  return normalizeRanges(out, length)
}

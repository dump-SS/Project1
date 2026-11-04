/**
 * markdown 快照的「渲染文本 ↔ 原文」映射（方案 C：保存时算好存起来）。
 *
 * 背景：契约规定高亮/虚化区间落在**原文**（markdown 源文本）上、按 Unicode 码点计
 * （lead-1 2026-11-02 拍板），但用户是在 react-markdown **渲染后的 DOM** 上划选。
 * 渲染会吃掉语法字符（`**`、反引号、代码围栏、表格管道符、链接 URL），
 * 渲染文本与原文不是同一串，所以必须有一张映射表。Skyer 2026-11-03 拍板方案 C：
 * **保存快照时一次性算好并存进 snapshot.sourceMap**，划选时查表，不实时算。
 *
 * ## 映射模型（已用探针坐实）
 *
 * react-markdown 渲染结果的 `textContent` 恰好等于 mdast 里
 * `text` / `inlineCode` / `code`（块级）三类节点值的**文档序拼接**：
 * 硬换行 `<br>`、链接 URL、图片 alt、表格管道符、列表符号都不进 textContent。
 * 于是映射 = 一串 chunk，每个 chunk 是一段「渲染区间 ↔ 原文区间」。
 *
 * chunk 内对齐分三种：
 * - `text`：通常 1:1；含转义（`\*`）或字符引用（`&amp;`）时源比渲染多字符，
 *   逐字符扫描产出 `jumps`（渲染偏移 → 累计多消耗的源码点数），可做到精确；
 * - `inlineCode` / `code`：常数偏移（去掉反引号围栏 / 代码围栏），精确；
 * - 扫描结果与节点值长度对不上时（未知语法），该 chunk 退化为 1:1 近似并在返回里计数，
 *   让调用方知道精度受损而不是静默出错。
 */
import remarkGfm from 'remark-gfm'
import remarkParse from 'remark-parse'
import remarkRehype from 'remark-rehype'
import { unified } from 'unified'
import type { CollectionSourceMap, CollectionSourceMapChunk } from '@/services/collection'

/** 线格式类型归 services/collection.ts（契约镜像），这里只起别名 */
export type SourceMapChunk = CollectionSourceMapChunk
export type SnapshotSourceMap = CollectionSourceMap

export interface BuildResult {
  map: SnapshotSourceMap
  /** 退化为近似的 chunk 数；0 = 全精确 */
  approxChunks: number
}

interface MdNode {
  type: string
  tagName?: string
  value?: string
  children?: MdNode[]
  position?: { start: { offset?: number }; end: { offset?: number } }
}

/** CommonMark 可转义字符集 */
const ESCAPABLE = /[!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~]/
const ENTITY_RE = /&(?:#[0-9]{1,7}|#x[0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});/y

const cpLen = (s: string) => Array.from(s).length

function scanTextAlignment(srcSlice: string, rendered: string): { jumps?: [number, number][]; ok: boolean } {
  const src = Array.from(srcSlice)
  const jumps: [number, number][] = []
  let si = 0
  let ri = 0
  let extra = 0
  while (si < src.length) {
    const ch = src[si]
    if (ch === '\\' && si + 1 < src.length && ESCAPABLE.test(src[si + 1])) {
      // 转义后的那个字符渲染在 ri，源里却在 si+1（反斜杠之后）——jump 记在 ri 上
      jumps.push([ri, extra + 1])
      si += 2
      ri += 1
      extra += 1
      continue
    }
    if (ch === '&') {
      // 注意 exec 的是切片串，sticky 的 lastIndex 必须从 0 起
      ENTITY_RE.lastIndex = 0
      const m = ENTITY_RE.exec(src.slice(si).join(''))
      if (m) {
        const consumed = cpLen(m[0])
        // 数字引用解码后 1 个码点；命名引用按 1 个码点计（HTML 命名引用绝大多数单字符）
        const decoded = 1
        jumps.push([ri, extra + (consumed - decoded)])
        si += consumed
        ri += decoded
        extra += consumed - decoded
        continue
      }
    }
    si += 1
    ri += 1
  }
  return { jumps: jumps.length ? jumps : undefined, ok: ri === cpLen(rendered) }
}

function fenceDelta(srcSlice: string, value: string, kind: 'inlineCode' | 'code'): number | null {
  if (kind === 'code') {
    const nl = srcSlice.indexOf('\n')
    if (nl >= 0 && srcSlice.startsWith(value, nl + 1)) return nl + 1
    const at = srcSlice.indexOf(value)
    return at >= 0 ? at : null
  }
  let k = 0
  while (k < srcSlice.length && srcSlice[k] === '`') k += 1
  if (k === 0) return null
  let inner = srcSlice.slice(k, srcSlice.length - k)
  let delta = k
  // CommonMark：内容首尾各一个空格且不全为空格时会被剥掉
  if (inner.length >= 2 && inner.startsWith(' ') && inner.endsWith(' ') && inner.trim() !== '') {
    if (inner.slice(1, -1) === value) return delta + 1
  }
  if (inner === value) return delta
  const at = srcSlice.indexOf(value)
  return at >= 0 ? at : null
}

/**
 * 保存快照时调用：解析 markdown，产出渲染文本 ↔ 原文的 chunk 映射。
 * plain 文本不需要映射（一一对应），不要调这个。
 */
export function buildSourceMap(markdown: string): BuildResult {
  const mdast = unified().use(remarkParse).use(remarkGfm).parse(markdown)
  // 走 hast 而不是 mdast：mdast-util-to-hast 会在块级兄弟之间插**合成换行文本节点**，
  // 它们进 DOM 的 textContent 却没有 position。映射的渲染空间必须和 textContent 严格同构，
  // 否则划选偏移整体漂移（真跑实测漂移量正好等于块间换行数）。
  const hast = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype)
    .runSync(mdast) as unknown as MdNode
  const chunks: SourceMapChunk[] = []
  let approxChunks = 0
  let cursor = 0

  const walk = (node: MdNode, fallback?: MdNode['position']) => {
    if (node.type === 'text') {
      const value = node.value ?? ''
      const rl = cpLen(value)
      // hast 里 inlineCode / 代码块的文本节点自身常无 position，位置在 code/pre 元素上
      const pos = node.position ?? fallback
      const start = pos?.start.offset
      const end = pos?.end.offset
      if (start === undefined || end === undefined) {
        // 合成换行节点：只推进渲染游标（它在 textContent 里占位），不产生 chunk
        cursor += rl
        return
      }
      const srcSlice = markdown.slice(start, end)
      if (srcSlice.startsWith('`')) {
        const delta = fenceDelta(srcSlice, value, srcSlice.startsWith('```') ? 'code' : 'inlineCode')
        if (delta === null) {
          approxChunks += 1
          chunks.push({ rs: cursor, rl, ss: start, sl: cpLen(srcSlice) })
        } else {
          chunks.push({ rs: cursor, rl, ss: start + delta, sl: rl })
        }
      } else {
        const { jumps, ok } = scanTextAlignment(srcSlice, value)
        if (!ok) approxChunks += 1
        chunks.push({ rs: cursor, rl, ss: start, sl: cpLen(srcSlice), jumps })
      }
      cursor += rl
      return
    }
    const own =
      node.type === 'element' && (node.tagName === 'code' || node.tagName === 'pre')
        ? node.position
        : undefined
    for (const child of node.children ?? []) walk(child, own ?? fallback)
  }
  walk(hast)

  // 渲染总长 = 游标终值（含块间合成换行），不是 chunk 长度和——
  // 划选偏移生活在 textContent 空间，夹取必须用同一个空间。
  const map: SnapshotSourceMap = { v: 1, chunks, total: cursor }
  return { map, approxChunks }
}

/** local 之前（不含 local 自己）累计多消耗的源码点数 */
function extraBefore(chunk: SourceMapChunk, local: number): number {
  if (!chunk.jumps) return 0
  let extra = 0
  for (const [at, cum] of chunk.jumps) {
    if (at < local) extra = cum
    else break
  }
  return extra
}

/** local 这个渲染字符自己多消耗的源码点数（转义 = 1，实体 = 消耗-1） */
function ownExtra(chunk: SourceMapChunk, local: number): number {
  if (!chunk.jumps) return 0
  const before = extraBefore(chunk, local)
  for (const [at, cum] of chunk.jumps) {
    if (at === local) return cum - before
  }
  return 0
}

/**
 * 渲染文本第 local 个码点在原文里占的码点区间 [s, e)。
 * 转义/实体字符会连语法字符一起返回（`\*` 两码点、`&amp;` 五码点）——
 * 否则按区间切原文渲染时，会漏出一个没被虚化盖住的反斜杠或分号残影。
 */
function charSpan(chunk: SourceMapChunk, local: number): [number, number] {
  const at = Math.min(Math.max(local, 0), Math.max(chunk.rl - 1, 0))
  const before = extraBefore(chunk, at)
  const s = chunk.ss + at + before
  return [s, s + 1 + ownExtra(chunk, at)]
}

function chunkAt(point: number, map: SnapshotSourceMap): SourceMapChunk {
  const { chunks } = map
  let target = chunks[chunks.length - 1]
  for (const c of chunks) {
    if (point < c.rs + c.rl) {
      target = c
      break
    }
    target = c
  }
  return target
}

/**
 * 把渲染文本上的码点区间换算成原文码点区间（半开）。
 * 起点取渲染首字符的源起点，终点取渲染末字符的源终点；
 * 跨 chunk 时中间被吃掉的语法字符自然落在区间内，符合直觉。
 */
export function renderedRangeToSource(
  start: number,
  end: number,
  map: SnapshotSourceMap,
): { start: number; end: number } {
  if (map.chunks.length === 0) return { start: 0, end: 0 }
  const total = renderedLength(map)
  const a = Math.min(Math.max(start, 0), total)
  const b = Math.min(Math.max(end, 0), total)
  const lo = Math.min(a, b)
  const hi = Math.max(a, b)
  const cLo = chunkAt(lo, map)
  const [s] = charSpan(cLo, lo - cLo.rs)
  if (hi === lo) return { start: s, end: s }
  const cHi = chunkAt(hi - 1, map)
  const [, e] = charSpan(cHi, hi - 1 - cHi.rs)
  return { start: s, end: e }
}

/** 渲染文本总码点长。优先用 total（含块间合成换行，与 textContent 同空间）；老映射没有则退化为 chunk 和 */
export function renderedLength(map: SnapshotSourceMap): number {
  return map.total ?? map.chunks.reduce((n, c) => n + c.rl, 0)
}

/** local 这个渲染字符消耗了几个源码点（1，或转义 2，或实体 n） */
function consumed(chunk: SourceMapChunk, local: number): number {
  return 1 + ownExtra(chunk, local)
}

/** chunk 内：源码点 local → 渲染 local（extraBefore 的逆） */
function localSourceToRendered(chunk: SourceMapChunk, local: number): number {
  for (let r = 0; r < chunk.rl; r += 1) {
    const spanStart = r + extraBefore(chunk, r)
    if (local >= spanStart && local < spanStart + consumed(chunk, r)) return r
  }
  return chunk.rl
}

/**
 * 原文码点 → 渲染码点（区间**起点**语义）：
 * 落在 chunk 间隙（语法字符 `**` / 围栏 / 管道符）时归到**下一个**渲染字符，
 * 这样「从语法字符开始选」的区间起点不会跑到文末去。
 */
export function sourcePointToRendered(point: number, map: SnapshotSourceMap): number {
  if (map.chunks.length === 0) return point
  for (const c of map.chunks) {
    if (point < c.ss) return c.rs
    if (point < c.ss + c.sl) return c.rs + localSourceToRendered(c, point - c.ss)
  }
  return renderedLength(map)
}

/**
 * 原文码点 → 渲染码点（区间**终点**语义，独占）：
 * 落在间隙时归到**上一个** chunk 的渲染末尾——「选到语法字符为止」等于选到它前面那个字。
 */
function sourcePointToRenderedEnd(point: number, map: SnapshotSourceMap): number {
  if (map.chunks.length === 0) return point
  for (const c of map.chunks) {
    if (point <= c.ss) return c.rs
    if (point <= c.ss + c.sl) return c.rs + localSourceToRendered(c, point - c.ss)
  }
  return renderedLength(map)
}

/**
 * 原文码点区间 → 渲染码点区间（renderedRangeToSource 的反向）。
 * 渲染 markdown 时按原文区间给文本节点包标记 span 要用；
 * 「全部虚化」存的 0..原文长 这种含全部语法字符的区间也靠这里正确落回渲染全文。
 */
export function sourceRangeToRendered(
  start: number,
  end: number,
  map: SnapshotSourceMap,
): { start: number; end: number } {
  if (map.chunks.length === 0) return { start: 0, end: 0 }
  const s = sourcePointToRendered(start, map)
  const e = sourcePointToRenderedEnd(end, map)
  return s <= e ? { start: s, end: e } : { start: e, end: s }
}

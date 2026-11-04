/**
 * rehype 插件：给 markdown 渲染结果套上高亮/虚化标记（#41）。
 *
 * 为什么走 rehype 而不是渲染后改 DOM：标记区间存在**原文**上，而渲染会吃掉语法字符，
 * 只能先把原文区间换算成渲染区间（sourceRangeToRendered），再在 hast 的文本节点上切分包裹。
 * 渲染后直接改 DOM 会和 React 的 reconciliation 打架（React 不知道插进来的 span），
 * 切源文本分段渲染又会在 `**` 中间切断语法，两条路都不通。
 *
 * 渲染文本偏移的口径与 markdownSourceMap 一致：hast 文本节点的文档序拼接 =
 * react-markdown 输出的 textContent（硬换行/链接 URL/表格管道符不进）。
 */
import type { CollectionSourceMap } from '@/services/collection'
import { sourceRangeToRendered } from './markdownSourceMap'

interface Range {
  start: number
  end: number
}

export interface SourceMarkOptions {
  map: CollectionSourceMap
  /** 原文码点区间 */
  highlights: Range[]
  blurs: Range[]
  /** CSS Modules 哈希后的类名由调用方传入，插件自己拿不到 */
  highlightClass: string
  blurClass: string
  /** 方向键焦点落在第几处虚化（按 blurs 排序后的序号）；-1 = 无焦点 */
  blurFocusedIndex: number
  /** 空格按住时临时解除焦点处虚化 */
  blurRevealed: boolean
  blurFocusedClass: string
  blurRevealedClass: string
}

interface HastNode {
  type: string
  value?: string
  tagName?: string
  properties?: Record<string, unknown>
  children?: HastNode[]
}

type RenderedMark = Range & { kind: 'highlight' | 'blur'; ordinal: number }

const cpLen = (s: string) => Array.from(s).length

export function rehypeSourceMarks(options: SourceMarkOptions) {
  const toRendered = (ranges: Range[], kind: 'highlight' | 'blur'): RenderedMark[] =>
    ranges
      .map((r, i) => ({ ...sourceRangeToRendered(r.start, r.end, options.map), kind, ordinal: i }))
      .filter((m) => m.end > m.start)

  // blur 优先：被虚化盖住的高亮没有意义（snapshotMarks.splitByMaps 同口径）
  const marks = [...toRendered(options.blurs, 'blur'), ...toRendered(options.highlights, 'highlight')]

  const classFor = (mark: RenderedMark): string[] => {
    if (mark.kind === 'highlight') return [options.highlightClass]
    const focused = mark.ordinal === options.blurFocusedIndex
    return [
      options.blurClass,
      ...(focused ? [options.blurFocusedClass] : []),
      ...(focused && options.blurRevealed ? [options.blurRevealedClass] : []),
    ]
  }

  return (tree: HastNode) => {
    if (marks.length === 0) return
    const root = tree
    let cursor = 0

    const wrapText = (node: HastNode, start: number): HastNode[] | null => {
      const chars = Array.from(node.value ?? '')
      const end = start + chars.length
      const cuts = new Set<number>([start, end])
      for (const m of marks) {
        if (m.start > start && m.start < end) cuts.add(m.start)
        if (m.end > start && m.end < end) cuts.add(m.end)
      }
      const sorted = [...cuts].sort((a, b) => a - b)
      const pieces: HastNode[] = []
      let marked = false
      for (let i = 0; i < sorted.length - 1; i += 1) {
        const a = sorted[i]
        const b = sorted[i + 1]
        const text = chars.slice(a - start, b - start).join('')
        const blur = marks.find((m) => m.kind === 'blur' && m.start <= a && b <= m.end)
        const mark = blur ?? marks.find((m) => m.start <= a && b <= m.end)
        if (mark) {
          marked = true
          pieces.push({
            type: 'element',
            tagName: 'span',
            properties: {
              className: classFor(mark),
            },
            children: [{ type: 'text', value: text }],
          })
        } else {
          pieces.push({ type: 'text', value: text })
        }
      }
      // 整节点被一个标记完整盖住时 cuts 只有首尾两点，但依然要包——不能按「切点数<=2」跳过
      return marked ? pieces : null
    }

    const walk = (node: HastNode) => {
      if (node.type === 'text') {
        const len = cpLen(node.value ?? '')
        const pieces = wrapText(node, cursor)
        cursor += len
        if (pieces) node.children = pieces // 文本节点临时挂 children，父级展开
        return
      }
      if (!node.children) return
      const next: HastNode[] = []
      for (const child of node.children) {
        walk(child)
        if (child.type === 'text' && child.children) {
          next.push(...child.children)
          delete child.children
        } else {
          next.push(child)
        }
      }
      node.children = next
    }

    walk(root)
  }
}

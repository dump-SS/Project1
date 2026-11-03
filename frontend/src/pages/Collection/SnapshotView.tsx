/**
 * 展开态的快照视图 + 「高亮 / 虚化」标记（#41，product-redesign-target.md §4.8.4 第 821-827 行）。
 *
 * 三条设计约束在这里落地：
 * - 第 821 行：**内容不可编辑**——本组件没有任何改正文的入口，标记只改显示
 * - 第 823 行：单条展开时**方向键**切换焦点至各处虚化，**空格**临时解除
 * - 第 826 行：「全部虚化」一键；**虚化状态需持久化**——每次改标记都 PATCH 全量区间
 * - 第 827 行：虚化不算编辑，所以标记与「不可编辑」不冲突
 *
 * ⚠️ 只对 `format: 'plain'` 的快照开放标记。契约规定区间落在**原文**上、按 Unicode 码点计，
 * 纯文本渲染时 host 的 textContent 与原文严格 1:1，偏移可直接算；markdown 渲染会吃掉
 * `**` / `#` / 表格管道符等语法字符，渲染文本与原文不是同一串，映射需要另做一套
 * 「渲染节点 → 源文本区间」的对照（lead-1 2026-11-02 预授权：太复杂就停下来报，
 * 可简化为只支持纯文本）。已在回执里报，未自行扩大范围。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import styles from './index.module.css'
import type { CollectionItem, CollectionItemUpdate } from '@/services/collection'
import {
  addRange,
  blurAll,
  countCodepoints,
  normalizeRanges,
  removeRange,
  splitByMarks,
  type MarkRange,
} from './snapshotMarks'
import { buildSourceMap, renderedRangeToSource } from '@/utils/markdownSourceMap'
import { rehypeSourceMarks } from '@/utils/rehypeSourceMarks'
import type { PluggableList } from 'unified'

interface SnapshotViewProps {
  item: CollectionItem
  busy: boolean
  /** 提交标记变更；契约定 highlights / blurStates 是**全量覆盖**，不是增量 */
  onPersist: (patch: CollectionItemUpdate) => void
}

export default function SnapshotView({ item, busy, onPersist }: SnapshotViewProps) {
  const { snapshot } = item
  const content = snapshot.content
  const isMarkdown = snapshot.format === 'markdown'

  const hostRef = useRef<HTMLDivElement | null>(null)
  /** 当前划选出的、还没落库的区间 */
  const [pending, setPending] = useState<MarkRange | null>(null)
  /** 方向键焦点落在第几处虚化上；-1 = 没有焦点 */
  const [focusIndex, setFocusIndex] = useState(-1)
  /** 空格按住时临时解除焦点处虚化（第 823 行） */
  const [revealed, setRevealed] = useState(false)

  const length = useMemo(() => countCodepoints(content), [content])
  const highlights = useMemo(
    () => normalizeRanges(item.highlights, length),
    [item.highlights, length],
  )
  const blurs = useMemo(() => normalizeRanges(item.blurStates, length), [item.blurStates, length])
  const segments = useMemo(
    () => splitByMarks(content, highlights, blurs),
    [content, highlights, blurs],
  )

  /** 每段的虚化序号（非虚化段为 -1），方向键按这个序号走 */
  const blurOrdinals = useMemo(() => {
    let n = 0
    return segments.map((s) => (s.kind === 'blur' ? n++ : -1))
  }, [segments])
  const blurCount = useMemo(() => blurOrdinals.filter((i) => i >= 0).length, [blurOrdinals])

  /**
   * 渲染↔原文映射。优先用快照里存好的那份（方案 C：保存时一次性算好，Skyer 2026-11-03 拍板）；
   * 老快照没有 sourceMap 时展开现算一次、只放内存——PATCH 不能改 snapshot，无法回填。
   */
  const map = useMemo(() => {
    if (!isMarkdown) return null
    return snapshot.sourceMap ?? buildSourceMap(content).map
  }, [isMarkdown, snapshot.sourceMap, content])

  /** markdown 渲染时按原文区间给文本节点包标记 span；plain 不需要（分段直渲） */
  const rehypePlugins = useMemo<PluggableList>(() => {
    if (!map) return []
    return [
      [
        rehypeSourceMarks,
        {
          map,
          highlights,
          blurs,
          highlightClass: styles.highlight,
          blurClass: styles.blur,
          blurFocusedIndex: focusIndex,
          blurRevealed: revealed,
          blurFocusedClass: styles.blurFocused,
          blurRevealedClass: styles.blurRevealed,
        },
      ] as PluggableList[number],
    ]
  }, [map, highlights, blurs, focusIndex, revealed])

  // 切换到另一条收藏时，上一条的临时状态不能带过来
  useEffect(() => {
    setPending(null)
    setFocusIndex(-1)
    setRevealed(false)
  }, [item.itemId])

  /**
   * 把 DOM 选区换算成原文的码点区间。
   *
   * plain：host 的 textContent 与 snapshot.content 完全相同，直接数码点。
   * markdown：textContent 是渲染结果，先数码点再查 sourceMap 换回原文（方案 C）。
   * 两种情况下标记条、提示文案都必须渲染在 host **外面**——host 内多一个字符，偏移就整体错位。
   */
  const captureSelection = useCallback(() => {
    const host = hostRef.current
    const selection = window.getSelection()
    if (!host || !selection || selection.isCollapsed || selection.rangeCount === 0) {
      setPending(null)
      return
    }
    const range = selection.getRangeAt(0)
    if (!host.contains(range.commonAncestorContainer)) {
      setPending(null)
      return
    }
    const before = document.createRange()
    before.selectNodeContents(host)
    before.setEnd(range.startContainer, range.startOffset)
    const renderedStart = countCodepoints(before.toString())
    const renderedEnd = renderedStart + countCodepoints(range.toString())
    if (renderedEnd <= renderedStart) {
      setPending(null)
      return
    }
    setPending(
      map
        ? renderedRangeToSource(renderedStart, renderedEnd, map)
        : { start: renderedStart, end: renderedEnd },
    )
  }, [map])

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      setPending(null)
      return
    }
    if (blurCount === 0) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
      e.preventDefault()
      setFocusIndex((i) => (i + 1) % blurCount)
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault()
      setFocusIndex((i) => (i <= 0 ? blurCount - 1 : i - 1))
    } else if (e.key === ' ') {
      // 空格临时解除：只对焦点那一处生效（自测用法是「聚焦一个空 → 看答案」）
      e.preventDefault()
      if (focusIndex >= 0) setRevealed(true)
    }
  }

  const onKeyUp = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === ' ') setRevealed(false)
  }

  const applyMark = (kind: 'highlight' | 'blur') => {
    if (!pending) return
    onPersist(
      kind === 'blur'
        ? { blurStates: addRange(item.blurStates, pending, length) }
        : { highlights: addRange(item.highlights, pending, length) },
    )
    setPending(null)
    window.getSelection()?.removeAllRanges()
  }

  const clearPendingMark = () => {
    if (!pending) return
    onPersist({
      highlights: removeRange(item.highlights, pending, length),
      blurStates: removeRange(item.blurStates, pending, length),
    })
    setPending(null)
    window.getSelection()?.removeAllRanges()
  }

  return (
    <div>
      <div
        ref={hostRef}
        className={`${styles.snapshot} ${styles.snapshotHost}`}
        tabIndex={0}
        role="group"
        aria-label="收藏快照全文。可划选文字做高亮或虚化标记；有虚化时方向键切换焦点、空格临时解除"
        onMouseUp={captureSelection}
        onKeyDown={onKeyDown}
        onKeyUp={onKeyUp}
      >
        {isMarkdown ? (
          <ReactMarkdown rehypePlugins={rehypePlugins}>{content}</ReactMarkdown>
        ) : (
          segments.map((seg, i) => {
          if (seg.kind === 'plain') return <span key={i}>{seg.text}</span>
          if (seg.kind === 'highlight') {
            return (
              <span key={i} className={styles.highlight}>
                {seg.text}
              </span>
            )
          }
          const focused = blurOrdinals[i] === focusIndex
          return (
            <span
              key={i}
              className={`${styles.blur} ${focused ? styles.blurFocused : ''} ${
                focused && revealed ? styles.blurRevealed : ''
              }`}
            >
              {seg.text}
            </span>
          )
          })
        )}
      </div>

      <div className={styles.markBar}>
        {pending ? (
          <>
            <span className={styles.markHint}>
              已选 {pending.end - pending.start} 字（原文第 {pending.start}–{pending.end} 码点）
            </span>
            <button
              type="button"
              className={styles.button}
              disabled={busy}
              onClick={() => applyMark('highlight')}
            >
              高亮
            </button>
            <button
              type="button"
              className={styles.button}
              disabled={busy}
              onClick={() => applyMark('blur')}
            >
              虚化
            </button>
            <button type="button" className={styles.button} disabled={busy} onClick={clearPendingMark}>
              取消这里的标记
            </button>
          </>
        ) : (
          <span className={styles.markHint}>
            {blurCount > 0
              ? `${blurCount} 处虚化 · 点进正文用方向键切焦点、空格临时解除`
              : '划选正文里的文字，可以高亮或虚化（虚化会存下来，下次打开还在）'}
          </span>
        )}
        <button
          type="button"
          className={styles.button}
          disabled={busy || length === 0}
          onClick={() => onPersist({ blurStates: blurAll(content) })}
        >
          全部虚化
        </button>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonDanger}`}
          disabled={busy || (highlights.length === 0 && blurs.length === 0)}
          onClick={() => onPersist({ highlights: [], blurStates: [] })}
        >
          清除全部标记
        </button>
      </div>

      {snapshot.imageRef && <ImageRefNote imageRef={snapshot.imageRef} />}
    </div>
  )
}

function ImageRefNote({ imageRef }: { imageRef: string }) {
  return (
    <p className={styles.markNote}>
      图片圈选收藏（引用 {imageRef}）——裁剪小图的展示要接 F 板块 GET /f/media/&#123;key&#125;，本单未接。
    </p>
  )
}

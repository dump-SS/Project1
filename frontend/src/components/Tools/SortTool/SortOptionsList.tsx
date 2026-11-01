/**
 * D58 /题目排序 · 内联四选项列表（F 板块）。
 *
 * 两处入口共用：
 * - 快捷引用面板「题目排序」Tab（B 面板经 renderSortTab 槽位注入，B 不认识 F）
 * - 拍题栏 SortMenuButton 的弹层
 *
 * 没图时置灰 + hover 提示（2026-11-01 用户拍板：disabled 项包一层带 title 的
 * span —— 原生 title 在部分浏览器对 disabled 按钮不弹，包在外层必弹）。
 * 任一点选都算「响应过光效引导」，消费掉仅首次标记。
 */
import { SORT_OPTIONS, markSortGlowDone } from './sortOptions'
import styles from './index.module.css'

interface SortOptionsProps {
  /** 有可排序的题图（调用方判定：拍题面板有 result / 快捷引用恰好一张媒体引用） */
  enabled: boolean
  /** 置灰时 hover 的提示文案（含原因） */
  disabledHint: string
  onQuickSort: (prompt: string) => void
  onCustomSort: (template: string) => void
  /** 点选后回调（快捷引用浮层用它关自己） */
  onPicked?: () => void
}

export default function SortOptions({
  enabled,
  disabledHint,
  onQuickSort,
  onCustomSort,
  onPicked,
}: SortOptionsProps) {
  const pick = (option: (typeof SORT_OPTIONS)[number]) => {
    markSortGlowDone()
    onPicked?.()
    if (option.template) {
      onCustomSort(option.template)
      return
    }
    if (option.prompt) onQuickSort(option.prompt)
  }

  return (
    <div className={styles.options} data-testid="sort-options">
      {SORT_OPTIONS.map((option) => (
        <span key={option.kind} className={styles.itemWrap} title={enabled ? undefined : disabledHint}>
          <button
            type="button"
            className={styles.item}
            disabled={!enabled}
            onClick={() => pick(option)}
            data-testid={`sort-option-${option.kind}`}
          >
            <span className={styles.itemLabel}>{option.label}</span>
            <span className={styles.itemDesc}>{option.desc}</span>
          </button>
        </span>
      ))}
      {!enabled && <p className={styles.hint}>{disabledHint}</p>}
    </div>
  )
}

/**
 * D58 · 拍题栏「题目排序」文字按钮 + 弹层菜单（F 板块）。
 *
 * 2026-11-01 用户拍板的入口形态之一：放在拍题/上传图片栏里（收起态与展开态
 * 各一枚，光效只在收起态——展开态本身就是用户正在和面板交互），按钮不用加号、
 * 直接叫「题目排序」。无图置灰 + hover 提示（disabledHint）。
 *
 * 首次拍照后光效引导（§4.10.4 第 881 行，仅一次）：光效由调用方以 glow prop
 * 打开；点开菜单即消费 SORT_GLOW_DONE_KEY（在 SortOptions 选中也会消费）。
 */
import { useEffect, useRef, useState } from 'react'
import SortOptionsList from './SortOptionsList'
import { hasSortGlowDone, markSortGlowDone } from './sortOptions'
import styles from './index.module.css'

interface SortMenuButtonProps {
  /** 有可排序的题图 */
  enabled: boolean
  /** 置灰时 hover 的提示文案 */
  disabledHint: string
  /** 首次拍照后的光效引导（仅首次，调用方控制是否点亮） */
  glow?: boolean
  onQuickSort: (prompt: string) => void
  onCustomSort: (template: string) => void
}

export default function SortMenuButton({
  enabled,
  disabledHint,
  glow = false,
  onQuickSort,
  onCustomSort,
}: SortMenuButtonProps) {
  const [open, setOpen] = useState(false)
  /** 光效实际点亮 = 调用方要亮 && 有图 && 「仅首次」标记还没被消费 */
  const [glowOn, setGlowOn] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // 首次拍照（enabled 翻 true）后点灯，除非引导已被消费过
  useEffect(() => {
    if (!glow || !enabled) {
      setGlowOn(false)
      return
    }
    if (!hasSortGlowDone()) setGlowOn(true)
  }, [glow, enabled])

  const consumeGlow = () => {
    markSortGlowDone()
    setGlowOn(false)
  }

  // 点外面收起
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next) consumeGlow()
  }

  return (
    <div className={styles.menuWrap} ref={wrapRef}>
      <button
        type="button"
        className={`${styles.textBtn} ${glowOn ? styles.glow : ''}`}
        onClick={toggle}
        disabled={!enabled}
        aria-expanded={open}
        title={enabled ? '对拍下的一页题目排序' : disabledHint}
        data-testid="sort-menu-button"
      >
        题目排序
      </button>
      {open && (
        <div className={styles.popover} role="menu" aria-label="题目排序" data-testid="sort-menu">
          <p className={styles.menuTitle}>/题目排序</p>
          <SortOptionsList
            enabled={enabled}
            disabledHint={disabledHint}
            onQuickSort={(prompt) => {
              setOpen(false)
              onQuickSort(prompt)
            }}
            onCustomSort={(template) => {
              setOpen(false)
              onCustomSort(template)
            }}
          />
        </div>
      )}
    </div>
  )
}

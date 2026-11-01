/**
 * D58 · /题目排序（F 板块，目标态 §4.10.4 第 879-892 行 + 派单技术路线）。
 *
 * 形态（按派单，flag 见交付报告）：输入框左侧**独立「+」按钮**，不并进
 * 快捷引用菜单、不碰已验证的拍题链路（MediaCapturePanel 零改动）。
 *
 * 交互：
 * - 点「+」→ 菜单含「/题目排序」四子选项（§4.10.4 第 884-889 行顺序）：
 *   难易排序 / 知识点掌握度排序 / 自定义排序 / 价值遴选
 * - 难易 / 掌握度 / 价值遴选 → 组排序 prompt 直接走既有 /chat/media 异步链路
 *   （已传图由 Chat 页 media 引用块携带；掌握度由 chat_engine 画像注入，无需新契约）
 * - 自定义 → 模板进输入框，用户续写后自己发
 * - 未拍题时四选项置灰 + 提示先拍题（§4.10.4「拍照后…多出」的防呆等价实现）
 * - 首次拍照后「+」出现光效引导（仅首次 = localStorage 持久化，跨会话只此一次）
 *
 * 适用场景是「一页多题」，prompt 文案里已含逐题排序要求（§4.10.4 第 891 行）。
 */
import { useEffect, useRef, useState } from 'react'
import styles from './index.module.css'

/** 光效引导「仅首次」的持久化 key */
export const SORT_GLOW_DONE_KEY = 'epochx:sort-glow-done'

interface SortOption {
  kind: 'difficulty' | 'mastery' | 'custom' | 'value'
  label: string
  desc: string
  /** 难易/掌握度/价值遴选：组好的 prompt，点击即随图发送 */
  prompt?: string
  /** 自定义：模板进输入框由用户续写 */
  template?: string
}

const SORT_OPTIONS: SortOption[] = [
  {
    kind: 'difficulty',
    label: '难易排序',
    desc: '按题目难度从易到难',
    prompt:
      '请对我拍的这一页题目按难度从易到难排序（一页里有多道题时给出逐题顺序），每题用一句话说明难度判断依据。',
  },
  {
    kind: 'mastery',
    label: '知识点掌握度排序',
    desc: '结合我的掌握度，差的排前面',
    prompt:
      '请结合我的知识点掌握度，对我拍的这一页题目排序：我掌握得差的排前面，逐题列出涉及的知识点和我的掌握情况。',
  },
  {
    kind: 'custom',
    label: '自定义排序',
    desc: '自己输入排序提示词',
    template: '请对我拍的这一页题目按以下要求排序：',
  },
  {
    kind: 'value',
    label: '价值遴选',
    desc: '知识点/解法交叉度高者优先',
    prompt:
      '请分析我拍的这一页里每道题涉及的知识点，指出哪些题的知识点/解法交叉度高，按刷题价值从高到低排序，并逐题说明价值理由。',
  },
]

interface SortToolProps {
  /** 输入框里是否已有拍题图片引用（F 媒体 chip） */
  hasMedia: boolean
  /** 难易/掌握度/价值遴选：点选后由 Chat 页组发（prompt 随已传图走异步链路） */
  onQuickSort: (prompt: string) => void
  /** 自定义：模板进输入框，用户续写后自己发 */
  onCustomSort: (template: string) => void
}

export default function SortTool({ hasMedia, onQuickSort, onCustomSort }: SortToolProps) {
  const [open, setOpen] = useState(false)
  const [glow, setGlow] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // 首次拍照 → 「+」出现光效引导（§4.10.4 第 881 行）；仅首次（localStorage 持久化）
  useEffect(() => {
    if (!hasMedia) return
    let done = false
    try {
      done = localStorage.getItem(SORT_GLOW_DONE_KEY) === '1'
    } catch {
      done = false
    }
    if (!done) setGlow(true)
  }, [hasMedia])

  // 菜单开着时点外面 → 收起
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const toggleMenu = () => {
    const next = !open
    setOpen(next)
    if (next && glow) {
      // 用户响应过引导（光效在展示中）→ 消失且不再出现。
      // ⚠️ 只在光效真实展示过时才落 flag：提前开过空菜单（还没拍照）不算，
      // 否则「首次拍照后出现光效」就被这次探索消耗掉了（§4.10.4 第 881 行）。
      setGlow(false)
      try {
        localStorage.setItem(SORT_GLOW_DONE_KEY, '1')
      } catch {
        // 隐私模式等写入失败：每会话重新引导一次，可接受
      }
    }
  }

  const pick = (option: SortOption) => {
    setOpen(false)
    if (option.template) {
      onCustomSort(option.template)
      return
    }
    if (option.prompt) onQuickSort(option.prompt)
  }

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={`${styles.plus} ${glow ? styles.glow : ''}`}
        onClick={toggleMenu}
        aria-label="题目排序"
        aria-expanded={open}
        title="题目排序"
        data-testid="sort-plus"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>

      {open && (
        <div className={styles.menu} role="menu" aria-label="题目排序" data-testid="sort-menu">
          <p className={styles.menuTitle}>/题目排序</p>
          {SORT_OPTIONS.map((option) => (
            <button
              key={option.kind}
              type="button"
              role="menuitem"
              className={styles.item}
              disabled={!hasMedia}
              onClick={() => pick(option)}
              data-testid={`sort-option-${option.kind}`}
            >
              <span className={styles.itemLabel}>{option.label}</span>
              <span className={styles.itemDesc}>{option.desc}</span>
            </button>
          ))}
          {!hasMedia && <p className={styles.hint}>先点「拍题」传一张题目照片，排序才有对象</p>}
        </div>
      )}
    </div>
  )
}

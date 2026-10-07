/**
 * DocsCopyMenu · 复制页面（2026-09-29 Skyer 指定）
 *
 * 分体钮：左半「复制」= 直接把当前页 Markdown 写入剪贴板；
 * 右半是下箭头，点开菜单：
 *   · 复制为 Markdown —— 与默认动作相同
 *   · 以 Markdown 格式查看 —— 弹层展示原始 Markdown（可复制、Esc/点遮罩关闭）
 *
 * 位置：文章页标题行最右侧（2026-09-30 Skyer 调整，原为标题左侧），
 * 由页面外壳经 DocsProse 的 actions 插槽传入。反馈照 §6 口径只说事实
 * （「已复制」），失败明说。hover：整组只描边高亮，悬停哪个钮哪个变暗；
 * 菜单从上滑出渐入，开启时下箭头翻向上。
 *
 * ⭐ 写在 components/Docs/：产品内长文将来复用同一件（「复制本文档」）。
 */
import { useEffect, useRef, useState } from 'react'
import styles from './DocsCopyMenu.module.css'

export interface DocsCopyMenuProps {
  /** 当前页原始 Markdown（registry 给的 body，不含 frontmatter） */
  markdown: string
  /** 页名，查看弹层里作副标题 */
  pageTitle: string
}

export default function DocsCopyMenu({ markdown, pageTitle }: DocsCopyMenuProps) {
  const [copied, setCopied] = useState<null | 'ok' | 'fail'>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [viewerOpen, setViewerOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const copiedTimer = useRef<number>(undefined)

  // 点组件外收菜单
  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [menuOpen])

  // 查看弹层开着时：Esc 关闭 + 锁背景滚动
  useEffect(() => {
    if (!viewerOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setViewerOpen(false)
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [viewerOpen])

  // 卸载时清掉「已复制」的计时器
  useEffect(() => () => window.clearTimeout(copiedTimer.current), [])

  const flashCopied = (ok: boolean) => {
    window.clearTimeout(copiedTimer.current)
    setCopied(ok ? 'ok' : 'fail')
    copiedTimer.current = window.setTimeout(() => setCopied(null), 1600)
  }

  const copyMarkdown = () => {
    copyText(markdown).then((ok) => flashCopied(ok))
  }

  return (
    <div className={styles.wrap} ref={menuRef}>
      <div className={styles.split}>
        <button
          type="button"
          className={styles.copyBtn}
          onClick={copyMarkdown}
          aria-label="复制本页 Markdown"
        >
          {copied === 'ok' ? <CheckIcon /> : <CopyIcon />}
          <span>{copied === 'ok' ? '已复制' : copied === 'fail' ? '复制失败' : '复制'}</span>
        </button>
        <button
          type="button"
          className={`${styles.arrowBtn}${menuOpen ? ' ' + styles.arrowOpen : ''}`}
          onClick={() => setMenuOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label="更多复制选项"
        >
          <ChevronDownIcon />
        </button>
      </div>

      {menuOpen && (
        <div className={styles.menu} role="menu" aria-label="复制选项">
          <button
            type="button"
            role="menuitem"
            className={styles.menuItem}
            onClick={() => {
              setMenuOpen(false)
              copyMarkdown()
            }}
          >
            复制为 Markdown
          </button>
          <button
            type="button"
            role="menuitem"
            className={styles.menuItem}
            onClick={() => {
              setMenuOpen(false)
              setViewerOpen(true)
            }}
          >
            以 Markdown 格式查看
          </button>
        </div>
      )}

      {viewerOpen && (
        <div className={styles.viewerLayer} role="dialog" aria-modal="true" aria-label="以 Markdown 格式查看当前页">
          <button
            type="button"
            className={styles.viewerScrim}
            aria-label="关闭查看"
            onClick={() => setViewerOpen(false)}
          />
          <div className={styles.viewer}>
            <header className={styles.viewerHead}>
              <div className={styles.viewerHeading}>
                <p className={styles.viewerKicker}>Markdown 源文</p>
                <p className={styles.viewerTitle}>{pageTitle}</p>
              </div>
              <div className={styles.viewerActions}>
                <button type="button" className={styles.viewerCopy} onClick={copyMarkdown}>
                  {copied === 'ok' ? '已复制' : '复制'}
                </button>
                <button
                  type="button"
                  className={styles.viewerClose}
                  aria-label="关闭"
                  onClick={() => setViewerOpen(false)}
                >
                  <CloseIcon />
                </button>
              </div>
            </header>
            <pre className={styles.viewerPre}>
              <code>{markdown}</code>
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

/** 剪贴板：优先 async API，非安全上下文（http 部署）降级 execCommand。 */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 走降级
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}

function CopyIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

function ChevronDownIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )
}

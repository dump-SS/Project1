/**
 * DocsTopbar · 文档站顶栏（2026-09-29 Skyer 指定）
 *
 * 布局：左 logo 全称（→ 官网 /）· 右上主题切换；搜索框居中，「索引」钮紧贴其左
 * （→ /docs 目录页，补上此前「文章页回不去索引」的缺口）。
 *
 * 视觉照 §8.4：与页面同一张底纸，只靠底部 hairline 分层，无玻璃无阴影；
 * 控件无衬线（§5 正在发生）；蓝色只出现在焦点 / hover（§4 蓝色出口）。
 *
 * 搜索是纯客户端（§14 的「客户端匹配」方案）：registry.searchPages 对
 * 38 篇的标题 + 正文做子串匹配，不引依赖、不上索引服务。
 * 键盘：↑↓ 选结果、Enter 跳转、Esc 收起；点击组件外收起。
 *
 * ⭐ 写在 components/Docs/：顶栏壳 + 搜索交互是产品内文档面板要复用的东西。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { searchPages, splitQueryTerms } from '../../../pages/Docs/registry'
import { useTheme } from '../../../context/ThemeContext.jsx'
import styles from './DocsTopbar.module.css'

export default function DocsTopbar() {
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const searchRef = useRef<HTMLDivElement>(null)

  const hits = useMemo(() => searchPages(query), [query])

  // 点击搜索区之外收起结果
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const resetSearch = () => {
    setQuery('')
    setOpen(false)
    setActive(0)
  }

  const go = (path: string) => {
    resetSearch()
    navigate(path)
  }

  const onSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open || hits.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, hits.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      const hit = hits[active]
      if (hit) go(hit.page.path)
    }
  }

  return (
    <header className={styles.topbar}>
      <div className={styles.inner}>
        <div className={styles.side}>
          <Link to="/" className={styles.brand} aria-label="EpochX 官网首页">
            {/* 日/夜两版全称 logo，由 [data-theme] 决定显隐（同 tokens 的跟随方式） */}
            <img className={styles.logoLight} src="/brand/logo-full-on-light-trim.png" alt="EpochX" />
            <img className={styles.logoDark} src="/brand/logo-full-on-dark-trim.png" alt="EpochX" />
          </Link>
        </div>

        <div className={styles.center}>
          <Link to="/docs" className={styles.indexBtn}>
            索引
          </Link>
          <div className={styles.searchWrap} ref={searchRef}>
            <div className={styles.searchBox}>
              <svg className={styles.searchIcon} viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path d="m21 21-4.35-4.35" />
              </svg>
              <input
                className={styles.searchInput}
                type="text"
                value={query}
                placeholder="搜索文档"
                aria-label="搜索文档"
                onChange={(e) => {
                  setQuery(e.target.value)
                  setOpen(e.target.value.trim() !== '')
                  setActive(0)
                }}
                onFocus={() => {
                  if (query.trim()) setOpen(true)
                }}
                onKeyDown={onSearchKeyDown}
              />
            </div>
            {open && (
              <div className={styles.results} aria-label="搜索结果">
                {hits.length === 0 ? (
                  <p className={styles.empty}>没有匹配「{query.trim()}」的页面。</p>
                ) : (
                  hits.map((hit, i) => (
                    <button
                      type="button"
                      key={hit.page.path}
                      className={`${styles.result}${i === active ? ' ' + styles.resultActive : ''}`}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => go(hit.page.path)}
                    >
                      <span className={styles.resultHead}>
                        <span className={styles.resultTitle}>{highlight(hit.page.title, query)}</span>
                        <span className={styles.resultSection}>{hit.page.sectionLabel}</span>
                      </span>
                      {hit.snippet && (
                        <span className={styles.resultSnippet}>{highlight(hit.snippet, query)}</span>
                      )}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        <div className={`${styles.side} ${styles.sideRight}`}>
          <button
            type="button"
            className={styles.themeBtn}
            onClick={toggleTheme}
            aria-label={theme === 'day' ? '切换到夜间模式' : '切换到日间模式'}
            title={theme === 'day' ? '切换到夜间模式' : '切换到日间模式'}
          >
            {theme === 'day' ? <MoonIcon /> : <SunIcon />}
          </button>
        </div>
      </div>
    </header>
  )
}

/** 命中词加粗（§8.1：不靠色块——mark 只抬字重，不着色）。 */
function highlight(text: string, query: string): ReactNode {
  const terms = splitQueryTerms(query)
  if (terms.length === 0) return text
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'))
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className={styles.hit}>
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

function SunIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

/**
 * DocsToc · 本页目录（visual-language §8.4.6 可复用）
 *
 * 从 markdown 正文的 h2/h3 抽出，靠 headingId 与 DocsProse 渲染出的 id 对齐。
 * activeId 由页面外壳的滚动跟随（scroll-spy）提供：当前读到的小节用
 * 蓝墨水左细条 + 文字转蓝标出（§8.4.4 当前项同款，§4 蓝色出口）。
 * 窄屏隐藏（由页面外壳的媒体查询控制，这里只负责结构与样式）。
 *
 * ⭐ 写在 components/ 而不是 Docs 页里：产品里的长文本侧栏目录是同一件东西。
 */
import type { ReactNode } from 'react'
import styles from './DocsToc.module.css'

export interface TocItem {
  id: string
  text: string
  level: 2 | 3
}

export interface DocsTocProps {
  items: TocItem[]
  title?: ReactNode
  /** 当前读到的小节 heading id；null/undefined = 还没进入任何小节 */
  activeId?: string | null
}

export default function DocsToc({ items, title = '本页', activeId }: DocsTocProps) {
  if (items.length === 0) return null
  return (
    <nav className={styles.toc} aria-label="本页目录">
      <p className={styles.tocTitle}>{title}</p>
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.id} className={item.level === 3 ? styles.nested : undefined}>
            <a
              className={`${styles.link}${item.id === activeId ? ' ' + styles.linkActive : ''}`}
              href={`#${item.id}`}
              aria-current={item.id === activeId ? 'location' : undefined}
            >
              {item.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}

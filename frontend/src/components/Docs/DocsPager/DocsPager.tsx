/**
 * DocsPager · 上一页 / 下一页（visual-language §8.4.6 可复用）
 *
 * 目录是唯一入口，页脚补一个线性翻页：改键盘 Tab 能走到（§9.1 判据——
 * 拿走鼠标这个功能还在吗？在）。
 *
 * ⭐ 写在 components/ 而不是 Docs 页里。
 */
import { Link } from 'react-router-dom'
import type { DocPage } from '../../../pages/Docs/registry'
import styles from './DocsPager.module.css'

export interface DocsPagerProps {
  prev?: DocPage
  next?: DocPage
}

export default function DocsPager({ prev, next }: DocsPagerProps) {
  if (!prev && !next) return null
  return (
    <nav className={styles.pager} aria-label="翻页">
      {prev ? (
        <Link className={`${styles.item} ${styles.prev}`} to={prev.path} rel="prev">
          <span className={styles.dir}>上一页</span>
          <span className={styles.title}>{prev.title}</span>
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link className={`${styles.item} ${styles.next}`} to={next.path} rel="next">
          <span className={styles.dir}>下一页</span>
          <span className={styles.title}>{next.title}</span>
        </Link>
      )}
    </nav>
  )
}

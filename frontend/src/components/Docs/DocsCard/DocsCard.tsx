/**
 * DocsCard · 卡片外壳（visual-language §8.4.6 可复用）
 *
 * 规矩照 §8.1 第 3 条：层级靠 hairline（1px 边框）+ 留白，**不靠色块分区、
 * 不靠阴影堆叠**——全页只有「底纸」和「白卡」两级（§3.1 判据）。
 * 圆角 8（§8.4.1），卡内留白 16。
 *
 * ⭐ 写在 components/ 而不是 Docs 页里：将来这就是产品内的卡片外壳。
 */
import type { ReactNode } from 'react'
import styles from './DocsCard.module.css'

export interface DocsCardProps {
  /** 卡片标题走无衬线（正在发生） */
  title?: ReactNode
  /** 右上角标识位：状态标签 / chip / 版本号等 */
  meta?: ReactNode
  children: ReactNode
  as?: 'div' | 'article' | 'li'
}

export default function DocsCard({ title, meta, children, as = 'div' }: DocsCardProps) {
  const Tag = as
  return (
    <Tag className={styles.card}>
      {(title || meta) && (
        <div className={styles.head}>
          {title && <h3 className={styles.title}>{title}</h3>}
          {meta && <div className={styles.meta}>{meta}</div>}
        </div>
      )}
      <div className={styles.body}>{children}</div>
    </Tag>
  )
}

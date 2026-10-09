/**
 * DocsCallout · 提示卡（visual-language §8.4.3）
 *
 * 规则照 §8.4.3，不自行发挥：
 * - 语义色沿用 §3：teal（说明）/ amber（注意）/ coral（提醒）
 * - 呈现用**左侧 3px 细条**或**小圆点 + 深色标题**，**不做整块底色**
 *   （与「层级靠 hairline、不用色块分区」同一条原则）
 * - 标题无衬线（正在发生/要看的），说明文字衬线（被写下来的）
 *
 * ⭐ 写在 components/ 而不是 Docs 页里（§8.4.6）：将来这就是产品内的提示卡组件。
 */
import type { ReactNode } from 'react'
import styles from './DocsCallout.module.css'

export type CalloutTone = 'note' | 'caution' | 'warn'

const TONE_CLASS: Record<CalloutTone, string> = {
  note: styles.toneNote,
  caution: styles.toneCaution,
  warn: styles.toneWarn,
}

const DEFAULT_TITLE: Record<CalloutTone, string> = {
  note: '说明',
  caution: '注意',
  warn: '提醒',
}

export interface DocsCalloutProps {
  tone?: CalloutTone
  /** 标题走无衬线；不传则用 tone 的默认标题 */
  title?: string
  children: ReactNode
}

export default function DocsCallout({ tone = 'note', title, children }: DocsCalloutProps) {
  return (
    <aside className={`${styles.callout} ${TONE_CLASS[tone]}`}>
      <p className={styles.title}>{title ?? DEFAULT_TITLE[tone]}</p>
      <div className={styles.body}>{children}</div>
    </aside>
  )
}

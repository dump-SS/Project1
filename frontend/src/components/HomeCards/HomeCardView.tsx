/**
 * 单张推荐卡。IntersectionObserver 只在这里接线，判定逻辑在 impressionReporter（纯函数、可单测）。
 * 点击 → onCardClick（D22：payload 作为结构化上下文注入对话）；划掉 → onDismiss（触发冷却）。
 */
import { useEffect, useRef } from 'react'
import styles from './index.module.css'
import {
  HOME_CARD_TYPE_LABEL,
  type HomeCard,
  type HomeCardGroup,
} from '@/services/homeCards'
import type { ShownEntryLike, ShownReporter } from './impressionReporter'

interface HomeCardViewProps {
  card: HomeCard
  group: HomeCardGroup
  reporter: ShownReporter
  onCardClick: (card: HomeCard, group: HomeCardGroup) => void
  onDismiss: (card: HomeCard, group: HomeCardGroup) => void
}

export default function HomeCardView({
  card,
  group,
  reporter,
  onCardClick,
  onDismiss,
}: HomeCardViewProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = hostRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => reporter(entries as unknown as ShownEntryLike[]),
      { threshold: [0, 0.5] },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [reporter])

  return (
    <div
      ref={hostRef}
      data-impression-key={`${group}:${card.fingerprint}`}
      className={styles.cardHost}
    >
      <button type="button" className={styles.card} onClick={() => onCardClick(card, group)}>
        <span className={styles.typeLabel}>{HOME_CARD_TYPE_LABEL[card.type]}</span>
        <span className={styles.cardTitle}>{card.display.title}</span>
        {card.display.subtitle && <span className={styles.cardSubtitle}>{card.display.subtitle}</span>}
      </button>
      <button
        type="button"
        className={styles.dismiss}
        onClick={() => onDismiss(card, group)}
        aria-label={`划掉这张${HOME_CARD_TYPE_LABEL[card.type]}卡`}
      >
        划掉
      </button>
    </div>
  )
}

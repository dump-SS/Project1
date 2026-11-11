/**
 * 首页推荐卡区取数 wrapper（D21/D28，契约 v1.21.0）。
 *
 * 上报口径（charter §四）：shown 只在卡片真正进视口时由 IntersectionObserver 触发、同卡去重；
 * clicked / dismissed 在交互时上报；fingerprint 原样回填不重算。
 * 后端生成候选时不记 shown（PR2 已按此实现），所以「克制出现」不会变成「生成即消耗名额」。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import styles from './index.module.css'
import HomeCardGroups from './HomeCardGroups'
import { createShownReporter } from './impressionReporter'
import {
  getHomeCards,
  reportCardImpression,
  type HomeCard,
  type HomeCardGroup,
  type HomeCardGroupResult,
} from '@/services/homeCards'

interface HomeCardsSectionProps {
  /** D22：点击把 payload 作为结构化上下文注入对话（由 Chat 页接既有引用块协议） */
  onCardClick: (card: HomeCard, group: HomeCardGroup) => void
  /** 空态可点击对话起点 */
  onStarter: (text: string) => void
}

export default function HomeCardsSection({ onCardClick, onStarter }: HomeCardsSectionProps) {
  const [groups, setGroups] = useState<HomeCardGroupResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const seenRef = useRef<Set<string>>(new Set())
  const cardsByKeyRef = useRef<Map<string, { card: HomeCard; group: HomeCardGroup }>>(new Map())

  useEffect(() => {
    const abort = new AbortController()
    getHomeCards(abort.signal)
      .then((res) => {
        const list = Array.isArray(res) ? res : []
        const byKey = new Map<string, { card: HomeCard; group: HomeCardGroup }>()
        for (const g of list) {
          for (const card of g.cards) byKey.set(`${g.group}:${card.fingerprint}`, { card, group: g.group })
        }
        cardsByKeyRef.current = byKey
        setGroups(list)
      })
      .catch((err) => {
        if (abort.signal.aborted) return
        setError(err instanceof Error ? err.message : '推荐卡加载失败')
      })
    return () => abort.abort()
  }, [])

  const reporter = useMemo(
    () =>
      createShownReporter(
        (key) => seenRef.current.has(key),
        (key) => seenRef.current.add(key),
        (key) => {
          const hit = cardsByKeyRef.current.get(key)
          if (!hit) return
          // 上报失败不阻断阅读；冷却少记一次好过把用户卡死在错误态
          void reportCardImpression({
            group: hit.group,
            cardType: hit.card.type,
            fingerprint: hit.card.fingerprint,
            action: 'shown',
          }).catch(() => {})
        },
      ),
    [],
  )

  const handleDismiss = useCallback((card: HomeCard, group: HomeCardGroup) => {
    void reportCardImpression({
      group,
      cardType: card.type,
      fingerprint: card.fingerprint,
      action: 'dismissed',
    }).catch(() => {})
    // 乐观移除：冷却生效前先把卡从眼前拿掉，刷新后后端也不会再给
    setGroups((prev) =>
      prev === null
        ? prev
        : prev
            .map((g) =>
              g.group === group
                ? { ...g, cards: g.cards.filter((c) => c.fingerprint !== card.fingerprint) }
                : g,
            )
            .filter((g) => g.cards.length > 0),
    )
  }, [])

  const handleClick = useCallback(
    (card: HomeCard, group: HomeCardGroup) => {
      void reportCardImpression({
        group,
        cardType: card.type,
        fingerprint: card.fingerprint,
        action: 'clicked',
      }).catch(() => {})
      onCardClick(card, group)
    },
    [onCardClick],
  )

  if (groups === null) return null
  if (error) return <div className={styles.error}>{error}</div>

  return (
    <div className={styles.section}>
      <HomeCardGroups
        groups={groups}
        reporter={reporter}
        onCardClick={handleClick}
        onDismiss={handleDismiss}
        onStarter={onStarter}
      />
    </div>
  )
}

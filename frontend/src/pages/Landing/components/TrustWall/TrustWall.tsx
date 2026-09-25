import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { TRUST_COPY } from '../../content/copy'
import { S5 } from '../../content/dialogues'
import { IconChevronDown } from '../../icons/UiIcons'
import { setHijackRange } from '../../lib/navScrollGuard'
import styles from './TrustWall.module.css'

/**
 * 信任屏（visual-language §7.6 / dev-spec §4.6）：
 * 横向劫持滚动（sticky 钉住一屏，纵向滚动驱动卡片横移）；
 * 三护栏：底部进度条 / 到底自动释放（sticky 跑道天然满足）/ 触控板横滑代理 + 方向键；
 * 卡片 hover/click/focus 三种触发展开；移动端配图不折叠 + 「展开」按钮；
 * 劫持区间注册给顶栏（区间内禁用收起/弹出）。
 */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

export default function TrustWall() {
  const reduced = useReducedMotion()
  const [runwayRef, progress] = useScrollProgress<HTMLDivElement>()
  const sectionRef = useRef<HTMLElement>(null)

  /* 注册劫持区间给顶栏（sticky 冻结纵向滚动的区间内顶栏常显） */
  useEffect(() => {
    if (reduced) return
    const el = runwayRef.current
    if (!el) return
    const register = () => {
      const rect = el.getBoundingClientRect()
      const top = rect.top + window.scrollY
      setHijackRange({ top, bottom: top + rect.height })
    }
    register()
    window.addEventListener('resize', register)
    return () => {
      window.removeEventListener('resize', register)
      setHijackRange(null)
    }
  }, [reduced, runwayRef])

  /* 触控板横滑代理：横向增量转纵向滚动（sticky 劫持期间生效） */
  useEffect(() => {
    if (reduced) return
    const el = sectionRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        window.scrollBy(0, e.deltaX * 1.3)
      }
      // 纵向滚轮不动：原生滚动本身驱动劫持，无需接管
    }
    el.addEventListener('wheel', onWheel, { passive: true })
    return () => el.removeEventListener('wheel', onWheel)
  }, [reduced])

  if (reduced) {
    /* 静态降级：纵向原生滚动，卡片全展开 */
    return (
      <section className={styles.staticSection} aria-label="隐私安全">
        <h2 className={styles.title}>{TRUST_COPY.title}</h2>
        <div className={styles.staticGrid}>
          {TRUST_COPY.cards.map((card) => (
            <TrustCard key={card.id} card={card} expanded />
          ))}
        </div>
      </section>
    )
  }

  const stripP = clamp01((progress - 0.05) / 0.75) // 卡片横移进度
  const trackShift = stripP * 62 // vh 单位的横移量（由卡片总宽决定）
  /* 标题随横移起步淡出：卡片会滑过标题区，标题不让位就会透过半透明卡面露字。
     淡出在卡 1 抵达标题区之前完成（前 25% 横移内），初始「sticky 在左」语义不变。 */
  const titleOpacity = 1 - clamp01(stripP / 0.25)

  return (
    <div className={styles.runway} ref={runwayRef}>
      <section className={styles.pin} ref={sectionRef} aria-label="隐私安全">
        <div className={`${styles.stage} landing-wrap`}>
          {/* 标题 sticky 在左 */}
          <div className={styles.titleBlock} style={{ opacity: titleOpacity }}>
            <h2 className={styles.title}>{TRUST_COPY.title}</h2>
          </div>

          {/* 卡片轨道：纵向滚动 → 横向位移 */}
          <div className={styles.viewport}>
            <div
              className={styles.track}
              style={{ transform: `translateX(calc(-${trackShift}vh))` }}
            >
              {TRUST_COPY.cards.map((card) => (
                <TrustCard key={card.id} card={card} />
              ))}
            </div>
          </div>
        </div>

        {/* 护栏①：底部进度条 */}
        <div className={styles.progressTrack} aria-hidden>
          <div className={styles.progressBar} style={{ width: `${stripP * 100}%` }} />
        </div>
      </section>
    </div>
  )
}

/* ---------------- 单卡 ---------------- */

function TrustCard({
  card,
  expanded = false,
}: {
  card: (typeof TRUST_COPY.cards)[number]
  expanded?: boolean
}) {
  const [open, setOpen] = useState(false)
  const isS5 = card.id === 'no-decide' // 卡 4：S5 对话（真实素材）
  const interactive = !expanded

  const toggle = () => {
    if (interactive) setOpen((v) => !v)
  }

  return (
    <article
      className={`${styles.card} ${open || expanded ? styles.cardOpen : ''}`}
      tabIndex={interactive ? 0 : -1}
      {...(interactive
        ? {
            onClick: toggle,
            onKeyDown: (e: React.KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                toggle()
              }
            },
            onFocus: () => setOpen(true),
          }
        : {})}
    >
      <div className={styles.cardHead}>
        <h3 className={styles.cardName}>{card.name}</h3>
        {/* 移动端「展开」按钮（配图不折叠，按钮只控制详情文字） */}
        {interactive && (
          <button
            type="button"
            className={styles.expandBtn}
            onClick={(e) => {
              e.stopPropagation()
              toggle()
            }}
            aria-expanded={open}
          >
            展开
            <IconChevronDown size={14} className={open ? styles.chevronUp : ''} />
          </button>
        )}
      </div>

      <p className={styles.cardBrief}>{card.brief}</p>

      {/* 配图区：卡 4 = S5 真对话；卡 1/2/3 = 占位块 + TODO（禁假界面图） */}
      <div className={`${styles.figure} ${open || expanded ? styles.figureOpen : ''}`}>
        {/* 0fr 折叠靠这一层零装饰裁剪（子元素自身的 margin/padding 会撑起轨道下限导致漏出） */}
        <div className={styles.figureClip}>
          {isS5 ? (
            <S5Preview />
          ) : (
            /* TODO(素材)：M1（X1 壳 + B 真链路）后替换真界面截图（dev-spec §5.3） */
            <div className={styles.placeholder} aria-label={`${card.name}（界面截图占位）`}>
              <span>界面截图 · 待接入</span>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

/* 卡 4 配图：S5 对话（跑批真素材，landing-conversation-samples.md §8） */
function S5Preview() {
  return (
    <div className={styles.s5} aria-label="真实对话示例">
      <p className={styles.s5User}>{S5.user}</p>
      {S5.product.map((line, i) => (
        <p key={i} className={styles.s5Product}>
          {line}
        </p>
      ))}
    </div>
  )
}

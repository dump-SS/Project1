import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { TRUST_COPY } from '../../content/copy'
import { S5 } from '../../content/dialogues'
import { IconChevronDown } from '../../icons/UiIcons'
import { IconLock, IconBars, IconReturn, IconShieldAlert } from '../../icons/TrustIcons'
import { setHijackRange } from '../../lib/navScrollGuard'
import styles from './TrustWall.module.css'

// Beams（React Bits，上游 r3f v9 仅 React 19 → 本仓裸 three 移植版）：
// 隐私安全页背景（2026-09-25 Skyer 指定），three 已在 deps
const Beams = lazy(() => import('../bits/Beams'))
// BorderGlow（React Bits，零依赖）：卡片辉光边框（2026-09-25 Skyer 指定）
import BorderGlow from '../bits/BorderGlow'

/**
 * 信任屏（2026-09-25 Skyer 定稿）：
 * 全页完整显示后再劫持横滚（stripP 起步 0.2）；标题不分行 + 下加小字；
 * 卡片 = BorderGlow 辉光边框，展开由 hover 触发（单开，不连锁），
 * 标题移到卡外左上，卡内左上为品牌色渐变图标。
 * 三护栏：底部进度条 / 到底自动释放 / 触控板横滑代理 + 方向键。
 */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
/** 线性映射 */
const map = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

/** 卡片图标映射（依次：锁头 / 柱状图 / 回箭头 / 带感叹号盾牌） */
const CARD_ICONS = {
  lock: IconLock,
  bars: IconBars,
  return: IconReturn,
  shield: IconShieldAlert,
} as const

export default function TrustWall() {
  const reduced = useReducedMotion()
  const [runwayRef, progress] = useScrollProgress<HTMLDivElement>()
  const sectionRef = useRef<HTMLElement>(null)
  /** 展开的卡片 id（单开，不连锁；hover / focus 触发） */
  const [openCard, setOpenCard] = useState<string | null>(null)

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
    }
    el.addEventListener('wheel', onWheel, { passive: true })
    return () => el.removeEventListener('wheel', onWheel)
  }, [reduced])

  if (reduced) {
    /* 静态降级：纵向原生滚动，卡片全展开 */
    return (
      <section className={styles.staticSection} aria-label="隐私安全">
        <h2 className={styles.title}>{TRUST_COPY.title}</h2>
        <p className={styles.sub}>{TRUST_COPY.sub}</p>
        <div className={styles.staticGrid}>
          {TRUST_COPY.cards.map((card) => (
            <TrustCard key={card.id} card={card} expanded />
          ))}
        </div>
      </section>
    )
  }

  /* 2026-09-25 Skyer：本页完整显示后再劫持横滚（起步 0.2，原 0.05 过早） */
  const stripP = map(progress, 0.2, 0.82) // 卡片横移进度
  const trackShift = stripP * 62 // vh 单位的横移量（由卡片总宽决定）
  /* 标题随横移起步淡出：卡片会滑过标题区，标题不让位就会透过半透明卡面露字。
     淡出在卡 1 抵达标题区之前完成（前 25% 横移内），初始「sticky 在左」语义不变。 */
  const titleOpacity = 1 - clamp01(stripP / 0.25)

  return (
    <div className={styles.runway} ref={runwayRef}>
      <section className={styles.pin} ref={sectionRef} aria-label="隐私安全">
        {/* 背景：Beams 光束（Skyer 2026-09-25；reduced-motion 不挂载，纯深底） */}
        {!reduced && (
          <div className={styles.beamsLayer} aria-hidden>
            <Suspense fallback={null}>
              <Beams
                beamWidth={2}
                beamHeight={15}
                beamNumber={12}
                lightColor="#4AD1FF" /* 品牌蓝光源 */
                beamColor="#0E1724"
                backgroundColor="#0B1017"
                speed={2}
                noiseIntensity={1.75}
                scale={0.2}
              />
            </Suspense>
          </div>
        )}
        <div className={`${styles.stage} landing-wrap`}>
          {/* 标题 sticky 在左（不分行）+ 标题下小字 */}
          <div className={styles.titleBlock} style={{ opacity: titleOpacity }}>
            <h2 className={styles.title}>{TRUST_COPY.title}</h2>
            <p className={styles.sub}>{TRUST_COPY.sub}</p>
          </div>

          {/* 卡片轨道：纵向滚动 → 横向位移；hover 出容器即收起（单开） */}
          <div className={styles.viewport} onMouseLeave={() => setOpenCard(null)}>
            <div
              className={styles.track}
              style={{ transform: `translateX(calc(-${trackShift}vh))` }}
            >
              {TRUST_COPY.cards.map((card) => (
                <TrustCard
                  key={card.id}
                  card={card}
                  open={openCard === card.id}
                  onOpen={() => setOpenCard(card.id)}
                  onClose={() => setOpenCard((cur) => (cur === card.id ? null : cur))}
                />
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
  open = false,
  onOpen,
  onClose,
}: {
  card: (typeof TRUST_COPY.cards)[number]
  expanded?: boolean
  open?: boolean
  onOpen?: () => void
  onClose?: () => void
}) {
  const isS5 = card.id === 'no-decide' // 卡 4：S5 对话（真实素材）
  const interactive = !expanded
  const isOpen = open || expanded
  const Icon = CARD_ICONS[card.icon]

  return (
    <div className={styles.cardCol}>
      {/* 卡片标题：移至卡外左上（Skyer 2026-09-25） */}
      <h3 className={styles.cardName}>{card.name}</h3>

      <BorderGlow
        className={styles.cardGlow}
        backgroundColor="rgba(27, 34, 45, 0.55)"
        borderRadius={16}
        glowColor="74 209 255" /* 品牌蓝 #4AD1FF */
        glowRadius={46}
        glowIntensity={1.1}
        coneSpread={32}
        colors={['#4AD1FF', '#1B5DBF', '#8FD3E8']}
        fillOpacity={0.42}
      >
        <article
          className={`${styles.card} ${isOpen ? styles.cardOpen : ''}`}
          tabIndex={interactive ? 0 : -1}
          {...(interactive
            ? {
                /* 展开改 hover 触发（Skyer 2026-09-25：不要 click；单开不连锁） */
                onMouseEnter: onOpen,
                onMouseLeave: onClose,
                onFocus: onOpen,
              }
            : {})}
        >
          {/* 卡内左上：品牌色渐变图标（依次：锁头 / 柱状图 / 回箭头 / 盾牌） */}
          <div className={styles.cardIcon}>
            <Icon size={28} />
          </div>

          <p className={styles.cardBrief}>{card.brief}</p>

          {/* 配图区：卡 4 = S5 真对话；卡 1/2/3 = 占位块 + TODO（禁假界面图） */}
          <div className={`${styles.figure} ${isOpen ? styles.figureOpen : ''}`}>
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

          {/* 移动端「展开」按钮（配图不折叠，按钮只控制详情文字） */}
          {interactive && (
            <button
              type="button"
              className={styles.expandBtn}
              onClick={(e) => {
                e.stopPropagation()
                isOpen ? onClose?.() : onOpen?.()
              }}
              aria-expanded={isOpen}
            >
              展开
              <IconChevronDown size={14} className={isOpen ? styles.chevronUp : ''} />
            </button>
          )}
        </article>
      </BorderGlow>
    </div>
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

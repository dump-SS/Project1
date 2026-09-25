import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useFlashlight, hasHoverPointer } from '../../hooks/useFlashlight'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useSloganSequence } from '../../hooks/useSloganSequence'
import { HERO_SLOGAN, HERO_ACTIONS, HERO_DRAFT_KEY } from '../../content/copy'
import {
  IconReportCard, IconBook, IconNotebook, IconPencil, IconRuler, IconCompass,
  IconTriangle, IconFlask, IconBeaker, IconTestTube, IconGlobe, IconMicroscope,
  IconStopwatch,
} from '../../icons/DarkMotifs'
import styles from './Hero.module.css'

const MOTIF_ICONS = [
  IconReportCard, IconBook, IconNotebook, IconPencil, IconRuler, IconCompass,
  IconTriangle, IconFlask, IconBeaker, IconTestTube, IconGlobe, IconMicroscope,
  IconStopwatch,
]

/** 暗纹散布：确定性伪随机布局（刷新不跳位） */
const MOTIF_SPOTS: Array<{
  icon: number
  x: number
  y: number
  size: number
  rotate: number
}> = Array.from({ length: 18 }, (_, i) => {
  const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1
  return {
    icon: Math.floor(r(1) * MOTIF_ICONS.length),
    x: 4 + r(2) * 92,
    y: 6 + r(3) * 84,
    size: 40 + Math.floor(r(4) * 44),
    rotate: Math.floor(r(5) * 70) - 35,
  }
})

export default function Hero() {
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const { text, youVisible, strongFrom, finished } = useSloganSequence()
  const sectionRef = useFlashlight<HTMLElement>(!reduced)
  const glowRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')

  // 光场交互：指针轻微推移（reduced-motion 不动）
  useEffect(() => {
    if (reduced || !hasHoverPointer()) return
    const el = sectionRef.current
    const glow = glowRef.current
    if (!el || !glow) return
    let raf = 0
    const onMove = (e: PointerEvent) => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const cx = window.innerWidth / 2
        const dx = (e.clientX - cx) / cx
        glow.style.transform = `translateX(${dx * 24}px)`
      })
    }
    el.addEventListener('pointermove', onMove)
    return () => {
      el.removeEventListener('pointermove', onMove)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [reduced, sectionRef])

  // 草稿恢复（跨登录墙：登录回来那句话还在）
  useEffect(() => {
    const saved = localStorage.getItem(HERO_DRAFT_KEY)
    if (saved) setDraft(saved)
  }, [])

  const onDraftChange = (v: string) => {
    setDraft(v)
    localStorage.setItem(HERO_DRAFT_KEY, v)
  }

  const goLogin = () => navigate('/login')

  // slogan：「你」高亮为蓝字（蓝字渲染辅助：在给定片段里拆出「你」）
  const renderWithYou = (s: string) => {
    const idx = youVisible ? s.indexOf('你') : -1
    if (idx < 0) return <span>{s}</span>
    return (
      <>
        <span>{s.slice(0, idx)}</span>
        <span className={styles.you}>{s[idx]}</span>
        <span>{s.slice(idx + 1)}</span>
      </>
    )
  }
  // 加粗段（新加的「围着你转」）：从 strongFrom 起、到该段结束为止（句号不加粗）
  const strongStart = strongFrom ?? -1
  const strongEnd = strongStart >= 0 ? strongStart + HERO_SLOGAN.strong.length : -1

  return (
    <section className={styles.hero} ref={sectionRef} aria-label="EpochX 学习状态智能助手">
      {/* 上部 2/3 光场：品牌蓝呼吸光晕（大面积低强度——作为「光」存在，visual-language §4） */}
      <div className={styles.glow} ref={glowRef} aria-hidden />

      {/* 暗纹层：流动的学习物件 monoline 线稿（静止近不可见，手电扫过显形） */}
      <div className={styles.motifs} aria-hidden>
        <div className={styles.motifsBase}>
          {MOTIF_SPOTS.map((s, i) => {
            const Icon = MOTIF_ICONS[s.icon]
            return (
              <Icon
                key={i}
                size={s.size}
                style={{
                  position: 'absolute',
                  left: `${s.x}%`,
                  top: `${s.y}%`,
                  transform: `rotate(${s.rotate}deg)`,
                }}
              />
            )
          })}
        </div>
        {/* 手电层：同一批线稿，径向 mask 只在指针附近显形（只属于 Hero，visual-language §8） */}
        <div className={styles.motifsTorch}>
          {MOTIF_SPOTS.map((s, i) => {
            const Icon = MOTIF_ICONS[s.icon]
            return (
              <Icon
                key={i}
                size={s.size}
                style={{
                  position: 'absolute',
                  left: `${s.x}%`,
                  top: `${s.y}%`,
                  transform: `rotate(${s.rotate}deg)`,
                }}
              />
            )
          })}
        </div>
      </div>

      {/* 底部地平线：左 logo + slogan，右动作区 */}
      <div className={`${styles.ground} landing-wrap`}>
        <div className={styles.left}>
          <img
            src="/brand/logo-full-on-dark-trim.png"
            alt="EpochX"
            className={styles.logo}
            height={62}
          />
          <h1 className={styles.slogan} aria-label={HERO_SLOGAN.final}>
            {strongStart >= 0 && text.length > strongStart ? (
              <>
                <span>{text.slice(0, strongStart)}</span>
                <span className={styles.sloganStrong}>
                  {renderWithYou(text.slice(strongStart, strongEnd))}
                </span>
                <span>{text.slice(strongEnd)}</span>
              </>
            ) : (
              renderWithYou(text)
            )}
            <span
              className={`lp-caret ${finished ? 'lp-caret--out' : ''}`}
              aria-hidden
            >
              |
            </span>
          </h1>
        </div>

        <div className={styles.actions}>
          {/* 三级阶梯：输入框（主焦点）→ 即刻开始（ghost）→ 桌面端（虚线灰空位） */}
          <input
            className={styles.input}
            type="text"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') goLogin()
            }}
            placeholder={HERO_ACTIONS.inputPlaceholder}
            aria-label={HERO_ACTIONS.inputPlaceholder}
          />
          <Link to="/login" className={styles.ghost}>
            {HERO_ACTIONS.primary}
          </Link>
          <span className={styles.desktop} aria-disabled="true" title="桌面端尚未推出">
            {HERO_ACTIONS.desktop}
          </span>
        </div>
      </div>
    </section>
  )
}

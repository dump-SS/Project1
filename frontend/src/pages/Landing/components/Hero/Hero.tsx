import { lazy, Suspense, useEffect, useRef, useState } from 'react'
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

// LaserFlow（React Bits，three）：Hero 光场底光。three 只进 landing-gfx chunk，
// 懒加载——CSS 呼吸光晕为第一帧与降级兜底（dev-spec §2.3 重背景先静态后增强）。
const LaserFlow = lazy(() => import('../bits/LaserFlow'))

const MOTIF_ICONS = [
  IconReportCard, IconBook, IconNotebook, IconPencil, IconRuler, IconCompass,
  IconTriangle, IconFlask, IconBeaker, IconTestTube, IconGlobe, IconMicroscope,
  IconStopwatch,
]

/** 暗纹散布：确定性伪随机布局（刷新不跳位）。
 *  2026-09-25 Skyer 调整：图标放大铺满、统一斜置（drift wall 形态，覆盖 §7.1 静止暗纹口径）。 */
const MOTIF_SPOTS: Array<{
  icon: number
  x: number
  y: number
  size: number
  rotate: number
}> = Array.from({ length: 26 }, (_, i) => {
  const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1
  return {
    icon: Math.floor(r(1) * MOTIF_ICONS.length),
    x: 1 + r(2) * 94,
    y: 2 + r(3) * 93,
    size: 96 + Math.floor(r(4) * 88),
    rotate: -34 + Math.floor(r(5) * 28),
  }
})

/** 单片暗纹墙（drift wall 拼贴单元，CSS 定尺寸；横向两片首尾相接做无缝漂移） */
function MotifSheet() {
  return (
    <div className={styles.wallSheet}>
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
  )
}

/** drift wall 漂移速度（px/s）——drift wall 级别的慢 */
const DRIFT_SPEED = 22

export default function Hero() {
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const { text, youVisible, strongFrom, finished } = useSloganSequence()
  const sectionRef = useFlashlight<HTMLElement>(!reduced)
  const glowRef = useRef<HTMLDivElement>(null)
  const driftBaseRef = useRef<HTMLDivElement>(null)
  const driftTorchRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')
  // LaserFlow 仅精确指针设备开启（触屏静态光晕——移动端简化，dev-spec §6）
  const laserOn = !reduced && hasHoverPointer()

  // drift wall 漂移：rAF 匀速横移，基底/手电双层同一帧写同一 transform 保证严丝合缝；
  // 触屏与 reduced-motion 静止
  useEffect(() => {
    if (reduced || !hasHoverPointer()) return
    const base = driftBaseRef.current
    const torch = driftTorchRef.current
    if (!base || !torch) return
    let raf = 0
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick)
      const sheet = base.firstElementChild as HTMLElement | null
      const w = sheet ? sheet.offsetWidth : 0
      if (!w) return
      const x = -((t / 1000 * DRIFT_SPEED) % w)
      const tf = `translate3d(${x}px, 0, 0)`
      base.style.transform = tf
      torch.style.transform = tf
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [reduced])

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
      {/* 光场：品牌蓝 LaserFlow 光束底光（懒加载 three，screen 混合隐黑底）；触屏/reduced 不挂载 */}
      {laserOn ? (
        <div className={styles.laserHost} aria-hidden>
          <Suspense fallback={null}>
            <LaserFlow
              color="#4AD1FF"
              backgroundColor="#000000"
              flowSpeed={0.32}
              fogIntensity={0.38}
              wispIntensity={2.8}
              flowStrength={0.22}
              verticalSizing={1.7}
              horizontalSizing={0.62}
              decay={1.45}
              mouseTiltStrength={0.02}
              dpr={1.5}
            />
          </Suspense>
        </div>
      ) : null}

      {/* 光场：大面积低强度品牌蓝光晕，呼吸 6–8s（第一帧兜底 + 深度层） */}
      <div className={styles.glow} ref={glowRef} aria-hidden />

      {/* 暗纹层：drift wall——放大铺满、斜置、缓慢漂移。
          基底低辨识常亮；手电层被径向 mask 包在未变换的层上（指针坐标即 mask 坐标），
          内部与基底同 rAF 同步漂移，显形位置始终跟随指针。 */}
      <div className={styles.motifs} aria-hidden>
        <div className={styles.motifsBase}>
          <div className={styles.drift} ref={driftBaseRef}>
            <MotifSheet />
            <MotifSheet />
          </div>
        </div>
        <div className={styles.motifsTorch}>
          <div className={styles.drift} ref={driftTorchRef}>
            <MotifSheet />
            <MotifSheet />
          </div>
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

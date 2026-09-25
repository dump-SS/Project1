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

// Prism（React Bits，ogl）：Hero 光场。ogl 与 Grainient 同库（已在 deps），懒加载——
// CSS 呼吸光晕为第一帧与降级兜底（dev-spec §2.3 重背景先静态后增强）。
const Prism = lazy(() => import('../bits/Prism'))

const MOTIF_ICONS = [
  IconReportCard, IconBook, IconNotebook, IconPencil, IconRuler, IconCompass,
  IconTriangle, IconFlask, IconBeaker, IconTestTube, IconGlobe, IconMicroscope,
  IconStopwatch,
]

/** 暗纹列配置：确定性伪随机（刷新不跳位）。
 *  2026-09-25 Skyer 调整：成列排布、整墙斜置、相邻列反向滚动（drift wall 列形态，
 *  覆盖 §7.1 静止暗纹口径）。 */
const MOTIF_SPOTS: Array<{ icon: number; size: number; rotate: number }> =
  Array.from({ length: 13 }, (_, i) => {
    const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1
    return {
      icon: i % MOTIF_ICONS.length,
      size: 132 + Math.floor(r(4) * 46),
      rotate: -16 + Math.floor(r(5) * 22),
    }
  })

const WALL_COLS = 12 // 列数（斜置 + inset 裁边后仍铺满超宽屏）
const CELLS_PER_COL = 6 // 每列半个循环的图标数（×2 拼接做无缝循环）

/** 单列暗纹：图标纵向循环带，偶数列向上 / 奇数列向下（2026-09-25 Skyer 指定错开方向） */
function MotifColumn({ col }: { col: number }) {
  // i 与 i+6 必须取同一图标（translateY(-50%) 无缝循环的前提）
  const cells = Array.from({ length: CELLS_PER_COL * 2 }, (_, i) => {
    const spot = MOTIF_SPOTS[(col * 3 + (i % CELLS_PER_COL) * 5) % MOTIF_SPOTS.length]
    return { ...spot, key: i }
  })
  return (
    <div
      className={`${styles.wallCol} ${col % 2 === 0 ? styles.colUp : styles.colDown}`}
      style={{ animationDelay: `${-(col * 3.7).toFixed(1)}s` }}
    >
      {cells.map((s, i) => {
        const Icon = MOTIF_ICONS[s.icon]
        return (
          <span key={i} className={styles.cell}>
            <Icon size={s.size} style={{ transform: `rotate(${s.rotate}deg)` }} />
          </span>
        )
      })}
    </div>
  )
}

export default function Hero() {
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const { text, youVisible, strongFrom, finished } = useSloganSequence()
  const sectionRef = useFlashlight<HTMLElement>(!reduced)
  const glowRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')
  // Prism 仅精确指针设备开启（触屏静态光晕——移动端简化，dev-spec §6）
  const prismOn = !reduced && hasHoverPointer()

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
      {/* 光场：Prism 棱镜光锥（懒加载 ogl，alpha 透明合成）；触屏/reduced 不挂载 */}
      {prismOn ? (
        <div className={styles.prismHost} aria-hidden>
          <Suspense fallback={null}>
            <Prism
              height={3.2}
              baseWidth={5.0}
              animationType="rotate"
              glow={1.0}
              noise={0.35}
              scale={3.2}
              hueShift={0}
              colorFrequency={0.9}
              bloom={1.1}
              timeScale={0.4}
              suspendWhenOffscreen
            />
          </Suspense>
        </div>
      ) : null}

      {/* 光场：大面积低强度品牌蓝光晕，呼吸 6–8s（第一帧兜底 + 深度层） */}
      <div className={styles.glow} ref={glowRef} aria-hidden />

      {/* 暗纹层：成列 drift wall——整墙斜置，偶数列向上 / 奇数列向下循环滚动。
          基底低辨识常亮；手电层被径向 mask 包在未变换的层上（指针坐标即 mask 坐标），
          内部列动画与基底同参数同帧启动，显形位置始终跟随指针。 */}
      <div className={styles.motifs} aria-hidden>
        <div className={styles.motifsBase}>
          <div className={styles.colsWrap}>
            {Array.from({ length: WALL_COLS }, (_, c) => (
              <MotifColumn key={c} col={c} />
            ))}
          </div>
        </div>
        <div className={styles.motifsTorch}>
          <div className={styles.colsWrap}>
            {Array.from({ length: WALL_COLS }, (_, c) => (
              <MotifColumn key={c} col={c} />
            ))}
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

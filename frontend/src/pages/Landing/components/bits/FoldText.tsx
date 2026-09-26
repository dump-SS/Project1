/**
 * FoldText —— 源自 React Bits（https://reactbits.dev，MIT + Commons Clause：
 * 产品内可用，禁止打包成组件库转售）。用于 CTA 末句入场（2026-09-25 Skyer 指定）。
 *
 * 本仓改动（逐条）：
 * 1. **去 gsap 依赖**：上游用 gsap timeline 驱动逐片折叠。`frontend/package.json`
 *    是共享独占文件（AGENTS.md 铁律 3）且仓库未安装 gsap，故改由 CSS 动画 +
 *    逐片 `animation-delay`（i × stagger）实现同一编排，节奏、折角、透视不变。
 * 2. **渐变字重实现**：上游的 `GradientText` 是「父元素 background-clip:text」做法，
 *    实测该裁剪**不作用于 3D 变换的子元素**（变换字片完全不显形，未变换的显形），
 *    因此两者无法嵌套。这里改为逐片按**实测横向偏移**拼出一条整行渐变
 *    （background-size = 行宽、background-position = −该片偏移），视觉配方同 GradientText。
 * 3. 样式改 CSS Module（上游注入全局 <style>，会与全站同名类互相污染）；
 *    `letter-spacing` 由上游的 -0.04em 改为继承，沿用页面既有 0.01em 口径。
 * 4. 缓动由 gsap `power3.out` 换成本仓通用 cubic-bezier(0.22, 1, 0.36, 1)。
 * 未改动：切分粒度（char/word/line）、hinge 折角与原点、透视、折痕明暗参数、
 * 无障碍处理（sr-only 原文 + 视觉层 aria-hidden）。
 */
import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import styles from './FoldText.module.css'

type SplitBy = 'char' | 'word' | 'line'
type Hinge = 'top' | 'bottom' | 'left' | 'right'

export interface FoldTextProps {
  text: string
  splitBy?: SplitBy
  hinge?: Hinge
  /** 单字片折叠时长（秒） */
  duration?: number
  /** 逐片延迟（秒） */
  stagger?: number
  perspective?: number
  creaseShading?: number
  fontSize?: string | number
  fontWeight?: string | number
  color?: string
  /** 品牌渐变（与 bits GradientText 同配方）：按字片实测偏移拼成整行渐变 */
  gradientColors?: readonly string[]
  className?: string
  style?: CSSProperties
}

/** 折角配置（原点 + 起始旋转，同上游） */
const HINGE_CONFIG: Record<Hinge, { origin: string; rotateX: number; rotateY: number }> = {
  top: { origin: '50% 0%', rotateX: -92, rotateY: 0 },
  bottom: { origin: '50% 100%', rotateX: 92, rotateY: 0 },
  left: { origin: '0% 50%', rotateX: 0, rotateY: 92 },
  right: { origin: '100% 50%', rotateX: 0, rotateY: -92 },
}

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

/** 空白段（保留空格与换行，同上游） */
const renderWhitespace = (value: string, key: string): ReactNode[] =>
  value.split(/(\n)/).map((part, index) => {
    if (part === '\n') return <br key={`${key}-br-${index}`} />
    if (!part) return null
    return (
      <span className={styles.whitespace} key={`${key}-space-${index}`}>
        {part.replace(/ /g, '\u00A0')}
      </span>
    )
  })

export default function FoldText({
  text,
  splitBy = 'char',
  hinge = 'top',
  duration = 0.65,
  stagger = 0.045,
  perspective = 700,
  creaseShading = 0.55,
  fontSize = 80,
  fontWeight = 800,
  color,
  gradientColors,
  className = '',
  style = {},
}: FoldTextProps) {
  const rootRef = useRef<HTMLSpanElement>(null)
  const visualRef = useRef<HTMLSpanElement>(null)
  const hingeConfig = HINGE_CONFIG[hinge] ?? HINGE_CONFIG.top
  const safeCrease = clamp(creaseShading, 0, 1)
  const safePerspective = Math.max(120, perspective)

  /* 逐片几何：行宽 + 每片横向偏移（只影响 X，3D 折角不动 X，故折叠中测量稳定） */
  const [geo, setGeo] = useState<{ width: number; offsets: number[] } | null>(null)

  useLayoutEffect(() => {
    if (!gradientColors?.length) {
      setGeo(null)
      return
    }
    const visual = visualRef.current
    if (!visual) return
    let alive = true
    const measure = () => {
      if (!alive || !visualRef.current) return
      const rootRect = visualRef.current.getBoundingClientRect()
      const pieces = Array.from(
        visualRef.current.querySelectorAll<HTMLElement>(`.${styles.piece}`),
      )
      setGeo({
        width: Math.max(1, rootRect.width),
        offsets: pieces.map((p) => p.getBoundingClientRect().left - rootRect.left),
      })
    }
    measure()
    // 自托管字体就绪后字宽会变，需重测（否则渐变错位）
    document.fonts?.ready.then(measure).catch(() => {})
    window.addEventListener('resize', measure)
    return () => {
      alive = false
      window.removeEventListener('resize', measure)
    }
  }, [gradientColors, text, splitBy, fontSize])

  const segments = useMemo(() => {
    let pieceIndex = -1

    const renderPiece = (content: string, key: string, split: SplitBy = splitBy) => {
      pieceIndex += 1
      const i = pieceIndex
      const pieceStyle: CSSProperties = {
        transformOrigin: hingeConfig.origin,
        '--fold-rx': `${hingeConfig.rotateX}deg`,
        '--fold-ry': `${hingeConfig.rotateY}deg`,
        '--fold-crease': safeCrease,
        '--fold-dur': `${duration}s`,
        '--fold-delay': `${(i * stagger).toFixed(3)}s`,
      } as CSSProperties
      if (geo) {
        const off = geo.offsets[i] ?? 0
        pieceStyle.backgroundSize = `${geo.width}px 100%`
        pieceStyle.backgroundPosition = `${-off}px 0`
      }
      return (
        <span
          className={styles.segment}
          data-fold-split={split}
          key={key}
          style={{ '--fold-perspective': `${safePerspective}px` } as CSSProperties}
        >
          <span
            className={`${styles.piece} ${gradientColors?.length ? styles.gradient : ''}`}
            data-hinge={hinge}
            style={pieceStyle}
          >
            {content || '\u00A0'}
          </span>
        </span>
      )
    }

    if (splitBy === 'line') {
      return text.split('\n').map((line, index) => (
        <span className={styles.line} key={`line-${index}`}>
          {renderPiece(line || '\u00A0', `segment-line-${index}`, 'line')}
        </span>
      ))
    }

    if (splitBy === 'word') {
      return text.split(/(\s+)/).flatMap((part, index) => {
        if (!part) return []
        if (/^\s+$/.test(part)) return renderWhitespace(part, `ws-${index}`)
        return renderPiece(part, `segment-word-${index}`)
      })
    }

    return Array.from(text).map((char, index) => {
      if (char === '\n') return <br key={`br-${index}`} />
      return renderPiece(char === ' ' ? '\u00A0' : char, `segment-char-${index}`)
    })
  }, [text, splitBy, hinge, hingeConfig, safePerspective, safeCrease, duration, stagger, gradientColors, geo])

  const rootStyle: CSSProperties = {
    '--fold-text-font-size': typeof fontSize === 'number' ? `${fontSize}px` : fontSize,
    '--fold-text-font-weight': fontWeight,
    ...(color ? { '--fold-text-color': color } : null),
    ...(gradientColors?.length
      ? { '--fold-text-gradient': `linear-gradient(to right, ${gradientColors.join(', ')})` }
      : null),
    ...style,
  } as CSSProperties

  return (
    <span ref={rootRef} className={`${styles.root} ${className}`.trim()} style={rootStyle}>
      <span className={styles.srOnly}>{text}</span>
      <span ref={visualRef} className={styles.visual} aria-hidden="true">
        {segments}
      </span>
    </span>
  )
}

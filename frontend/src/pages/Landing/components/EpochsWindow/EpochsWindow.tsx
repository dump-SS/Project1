import { lazy, Suspense, useEffect, useState } from 'react'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { EPOCHS_COPY } from '../../content/copy'
import styles from './EpochsWindow.module.css'

// ColorBends（React Bits，three）：logo 窗背景彩色弯折光带（2026-09-25 Skyer 指定）。
// three 只进 landing-gfx chunk；进度过半（logo 临近入窗）才挂载。
const ColorBends = lazy(() => import('../bits/ColorBends'))

/**
 * 第二屏 · 三时代（2026-09-25 Skyer 定稿编排）：
 * 滑动窗口直接全屏（100vw×100%，左侧顶屏幕边缘）——三格横移即「滑出」，
 * ColorBends 画布随轨道平移揭幕，全程零 resize。
 * 左侧文字连同左半屏 = 直角梯形斜切卡片（右缘斜切）盖在轨道上；
 * logo 滑入约 75% 后整卡向右滑出屏幕 → 背景完全展示、logo 恰好居中；
 * 继续滚动 logo 放大（滚动驱动）。
 */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
/** 线性映射 */
const map = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

/** 斜切卡片向左滑出的触发进度（Skyer 2026-09-25：触发晚一些）与回滚复位阈值 */
const CARD_OFF_ON = 0.68
const CARD_OFF_OFF = 0.58

export default function EpochsWindow() {
  const reduced = useReducedMotion()
  const [ref, progress] = useScrollProgress<HTMLDivElement>()
  const [cardOff, setCardOff] = useState(false)

  /* 卡片滑出/复位（滞回）——一次性滑出，不随滚动往返抖动 */
  useEffect(() => {
    if (reduced) return
    if (progress >= CARD_OFF_ON) setCardOff(true)
    else if (progress < CARD_OFF_OFF) setCardOff(false)
  }, [progress, reduced])

  /* ColorBends：进度过半才挂载（three chunk 懒加载）；随轨道平移渐显 */
  const cbOn = progress > 0.32
  const cbReveal = map(progress, 0.3, 0.5)

  /* logo 放大：卡片滑出、背景完全展示后（Skyer：再滑动页面，logo 放大） */
  const logoScale = 1 + map(progress, 0.78, 0.92) * 0.5

  if (reduced) {
    // 静态降级：三格并排 + logo 定格（无滚动跑道）
    return (
      <section className={styles.staticSection} aria-label="三时代">
        <div className={`${styles.staticGrid} landing-wide`}>
          <div className={styles.staticFrame}><span>古代书简</span></div>
          <div className={styles.staticFrame}><span>书山题海</span></div>
          <div className={styles.staticFrameLogo}>
            <img src="/brand/logo-full-on-dark-trim.png" alt="EpochX" height={44} />
          </div>
        </div>
        <div className={`${styles.copy} landing-wide`}>
          <Copy />
        </div>
      </section>
    )
  }

  // 滚动编排：0.08–0.78 窗内横滚（书简→题海→logo 居中）
  const stripP = map(progress, 0.08, 0.78) // 窗内横滚进度
  const lightP = map(progress, 0.3, 0.6) // 光回归（logo 入窗即转亮）
  const dim = cardOff ? 0 : 1 - lightP // 历史段收暗系数（卡片滑出后光全开）

  return (
    <div className={styles.runway} ref={ref}>
      <section className={styles.pin} aria-label="三时代">
        {/* 全屏滑动窗口：三格横移，左侧顶屏幕边缘（Skyer 2026-09-25） */}
        <div
          className={styles.track}
          /* track 宽 = 3 屏（300%），百分比相对自身 → 三格全程序 = -66.67%（logo 恰好居中） */
          style={{ transform: `translateX(${-stripP * 66.6667}%)` }}
        >
          <div className={styles.frame}>
            {/* 实景图：古代书简（Skyer 2026-09-25 提供入页） */}
            <div className={styles.slide}>
              <img
                src="/slides/epoch-bamboo.jpg"
                alt="古代书简——竹简、毛笔与烛台"
                className={styles.slideImg}
              />
              <div className={styles.slideTint} aria-hidden />
            </div>
          </div>
          <div className={styles.frame}>
            {/* 实景图：书山题海（Skyer 2026-09-25 提供入页） */}
            <div className={styles.slide}>
              <img
                src="/slides/epoch-papers.jpg"
                alt="书山题海——堆叠的课本与写满批注的试卷"
                className={styles.slideImg}
              />
              <div className={styles.slideTint} aria-hidden />
            </div>
          </div>
          <div className={`${styles.frame} ${styles.frameLogo}`}>
            {/* ColorBends 背景：随轨道平移从右侧滑入，画布全屏零 resize（Skyer 2026-09-25） */}
            <div className={styles.cbHost} style={{ opacity: cbReveal }} aria-hidden>
              {cbOn ? (
                <Suspense fallback={null}>
                  <ColorBends
                    colors={['#4AD1FF', '#1B5DBF', '#8FD3E8']}
                    transparent={false}
                    speed={0.25}
                    scale={1.35}
                    noise={0.28}
                    intensity={1.2}
                    bandWidth={5}
                    iterations={2}
                  />
                </Suspense>
              ) : (
                <div className={styles.cbFallback} />
              )}
            </div>
            <img
              src="/brand/logo-full-on-dark-trim.png"
              alt="EpochX"
              height={56}
              style={{ transform: `scale(${logoScale})` }}
            />
          </div>
        </div>

        {/* 左侧斜切卡片：直角梯形（右缘斜切、左缘顶屏幕边缘），承载文字；
            logo 滑入约 75% 后整卡向右滑出屏幕（Skyer 2026-09-25） */}
        <div className={`${styles.card} ${cardOff ? styles.cardOff : ''}`}>
          <div className={styles.cardInner}>
            <Copy />
          </div>
        </div>

        {/* 光的调度：历史段主光收暗（沉蓝）→ 卡片滑出后光全开 */}
        <div
          className={styles.lightVeil}
          style={{ opacity: dim * 0.42 }}
          aria-hidden
        />
      </section>
    </div>
  )
}

function Copy() {
  const text = EPOCHS_COPY.headline
  const youIdx = text.indexOf(EPOCHS_COPY.highlight)
  // 2026-09-25 Skyer：标题在逗号后换行（两行），字号加大加粗；「构建」不折行
  const commaIdx = text.indexOf('，')
  const line1 = commaIdx >= 0 ? text.slice(0, commaIdx + 1) : ''
  const rest = commaIdx >= 0 ? text.slice(commaIdx + 1) : text

  const renderYou = (s: string) => {
    const idx = s.indexOf(EPOCHS_COPY.highlight)
    if (idx < 0) return <span>{s}</span>
    return (
      <>
        <span>{s.slice(0, idx)}</span>
        <span className={styles.you}>{s[idx]}</span>
        <span>{s.slice(idx + 1)}</span>
      </>
    )
  }

  return (
    <div>
      <h2 className={styles.headline}>
        {commaIdx >= 0 && youIdx > commaIdx ? (
          <>
            <span className={styles.headlineLine}>{line1}</span>
            <span className={styles.headlineLine}>{renderYou(rest)}</span>
          </>
        ) : (
          renderYou(text)
        )}
      </h2>
      <p className={styles.sub}>{EPOCHS_COPY.sub}</p>
    </div>
  )
}

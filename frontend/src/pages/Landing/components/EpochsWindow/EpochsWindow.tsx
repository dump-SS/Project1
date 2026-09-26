import { lazy, Suspense, useEffect, useState } from 'react'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { EPOCHS_COPY } from '../../content/copy'
import styles from './EpochsWindow.module.css'

// ColorBends（React Bits，three）：logo 窗背景彩色弯折光带（2026-09-25 Skyer 指定）。
// three 只进 landing-gfx chunk；进度过半（logo 临近入窗）才挂载。
const ColorBends = lazy(() => import('../bits/ColorBends'))

/**
 * 第二屏 · 三时代（visual-language §7.2 / dev-spec §4.2）：
 * 斜向平行四边形视窗，窗内横向流动：古代书简 → 书山题海 → logo。
 * 2026-09-25 Skyer 定稿编排：logo 滑入约 80% 时触发【固定时序动效】——
 * 平行四边形展平为全屏矩形、logo 回中放大、ColorBends 完整展出；
 * 终段不随用户滚动实时改变窗口尺寸（滚动只负责触发，动画一次性播完）。
 * ColorBends 画布固定全屏尺寸居中放置，只被「揭幕」不被 resize（消除卡顿根源）。
 */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
/** 线性映射 */
const map = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

/** 触发固定动效的滚动进度：logo 滑入约 80%（stripP≈0.8 → progress≈0.66） */
const FINAL_ON = 0.66
const FINAL_OFF = 0.56 /* 回滚复位阈值（滞回，防抖） */

export default function EpochsWindow() {
  const reduced = useReducedMotion()
  const [ref, progress] = useScrollProgress<HTMLDivElement>()
  const [final, setFinal] = useState(false)

  /* 触发/复位（滞回）——滚动只负责触发，触发后动画按固定时序播完 */
  useEffect(() => {
    if (reduced) return
    if (progress >= FINAL_ON) setFinal(true)
    else if (progress < FINAL_OFF) setFinal(false)
  }, [progress, reduced])

  /* ColorBends：进度过半（logo 临近入窗）才挂载（three chunk 懒加载）；
     画布固定全屏尺寸，透明度随 logo 滑入渐显 */
  const cbOn = progress > 0.5
  const cbReveal = map(progress, 0.5, 0.68)

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

  // 滚动编排：0–0.15 进入 → 0.1–0.8 窗内横滚（书简→题海→logo 80%）
  // → progress≥0.66 触发固定动效（CSS 过渡一次性播完，不随滚动回放）
  const stripP = map(progress, 0.1, 0.8) // 窗内横滚进度
  const lightP = map(progress, 0.38, 0.7) // 光回归（logo 开始入窗即转亮）
  const dim = final ? 0 : 1 - lightP // 历史段收暗系数（触发后光全开）

  return (
    <div className={`${styles.runway} ${final ? styles.final : ''}`} ref={ref}>
      <section className={`${styles.pin} ${final ? styles.pinFinal : ''}`} aria-label="三时代">
        <div className={`${styles.stage} landing-wide`}>
          {/* 斜向平行四边形视窗：触发后经 CSS 过渡展平为全屏矩形（Skyer 2026-09-25） */}
          <div className={styles.window}>
            <div
              className={styles.track}
              /* track 宽 = 3 窗（300%），百分比相对自身 → 三格全程序 = -66.67% */
              style={{ transform: `translateX(${-stripP * 66.6667}%)` }}
            >
              {/* 三格：古代书简（占位）→ 书山题海（占位）→ logo（原色） */}
              <div className={styles.frame}>
                {/* TODO(素材)：实景图占位——古代书简，横构图 3:2、暗蓝 duotone、商用授权（D6） */}
                <div className={styles.ph} aria-label="古代书简（实景图占位）">
                  <span>古代书简</span>
                </div>
              </div>
              <div className={styles.frame}>
                {/* TODO(素材)：实景图占位——书山题海（建议团队自拍学生真试卷堆）（D6） */}
                <div className={styles.ph} aria-label="书山题海（实景图占位）">
                  <span>书山题海</span>
                </div>
              </div>
              <div className={`${styles.frame} ${styles.frameLogo}`}>
                {/* ColorBends 画布固定全屏尺寸居中放置：只被「揭幕」不被 resize */}
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
                <img src="/brand/logo-full-on-dark-trim.png" alt="EpochX" height={56} />
              </div>
            </div>
            {/* 光的调度：历史段主光收暗（沉蓝，内容仍隐约可读）→ logo 显现瞬间光回归 */}
            <div
              className={styles.lightVeil}
              style={{ opacity: dim * 0.42 }}
              aria-hidden
            />
          </div>

          {/* 文案：固定动效触发后淡出让位（终态全屏矩形 + logo 沉浸画面） */}
          <div className={styles.copy}>
            <Copy />
          </div>
        </div>
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

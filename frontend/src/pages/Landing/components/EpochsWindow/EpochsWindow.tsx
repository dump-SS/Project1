import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { EPOCHS_COPY } from '../../content/copy'
import styles from './EpochsWindow.module.css'

/**
 * 第二屏 · 三时代（visual-language §7.2 / dev-spec §4.2）：
 * 斜向平行四边形窄视窗（斜角≈logo X 斜体），窗内横向流动：
 * 古代书简 → 书山题海 → logo；logo 入窗后视窗右移 + 横向扩大；
 * 历史段主光收暗，logo 显现时光回归（你的时代有光）。
 * 实现：sticky + scroll progress，不全页劫持；reduced-motion → 三格静态。
 */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
/** 线性映射 */
const map = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

export default function EpochsWindow() {
  const reduced = useReducedMotion()
  const [ref, progress] = useScrollProgress<HTMLDivElement>()

  if (reduced) {
    // 静态降级：三格并排 + logo 定格（无滚动跑道）
    return (
      <section className={styles.staticSection} aria-label="三时代">
        <div className={`${styles.staticGrid} landing-wrap`}>
          <div className={styles.staticFrame}><span>古代书简</span></div>
          <div className={styles.staticFrame}><span>书山题海</span></div>
          <div className={styles.staticFrameLogo}>
            <img src="/brand/logo-full-on-dark-trim.png" alt="EpochX" height={44} />
          </div>
        </div>
        <div className={`${styles.copy} landing-wrap`}>
          <Copy />
        </div>
      </section>
    )
  }

  // 滚动编排：0–0.15 进入 → 0.15–0.75 窗内横滚（书简→题海→logo）→ 0.6–1.0 logo 入窗后视窗右移扩大 + 光回归
  const stripP = map(progress, 0.1, 0.8) // 窗内横滚进度
  const expandP = map(progress, 0.62, 0.95) // 视窗右移 + 扩大
  const lightP = map(progress, 0.55, 0.85) // 光回归
  const dim = 1 - lightP // 历史段收暗系数

  return (
    <div className={styles.runway} ref={ref} /* 高度 = 视口 + 滚动跑道 */>
      <section className={styles.pin} aria-label="三时代">
        <div className={`${styles.stage} landing-wrap`}>
          {/* 斜向平行四边形视窗：宽度随 expandP 扩大、整体右移 */}
          <div
            className={styles.window}
            style={{
              width: `calc(38% + ${expandP * 16}%)`,
              transform: `translateX(${expandP * 8}%)`,
            }}
          >
            <div
              className={styles.track}
              style={{ transform: `translateX(${-stripP * 200}%)` }}
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
                <img src="/brand/logo-full-on-dark-trim.png" alt="EpochX" height={56} />
              </div>
            </div>
            {/* 光的调度：历史段主光收暗 → logo 显现瞬间光回归 */}
            <div
              className={styles.lightVeil}
              style={{ opacity: dim * 0.72 }}
              aria-hidden
            />
          </div>

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
  return (
    <div>
      <h2 className={styles.headline}>
        <span>{text.slice(0, youIdx)}</span>
        <span className={styles.you}>{text[youIdx]}</span>
        <span>{text.slice(youIdx + 1)}</span>
      </h2>
      <p className={styles.sub}>{EPOCHS_COPY.sub}</p>
    </div>
  )
}

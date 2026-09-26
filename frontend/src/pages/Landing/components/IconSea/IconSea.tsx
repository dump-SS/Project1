import { useReducedMotion } from '../../hooks/useReducedMotion'
import { ICON_SEA_COPY } from '../../content/copy'
import { SEA_ICONS } from '../../icons/FeatureIcons'
import { LogoLoop } from '../bits/LogoLoop'
import styles from './IconSea.module.css'

/**
 * 图标海屏（2026-09-25 Skyer 调整）：
 * 功能图标按「学生的一天」顺序横向无缝循环——改用 bits LogoLoop
 * （speed 80 / hoverSpeed 30），每个单元格叠加**逐个上下浮动**（波浪，逐项延迟）。
 * 配文把中心拉回「你」，否则这屏就变成功能罗列页。
 */
export default function IconSea() {
  const reduced = useReducedMotion()
  const text = ICON_SEA_COPY.caption
  const youIdx = text.indexOf(ICON_SEA_COPY.highlight)

  const logos = SEA_ICONS.map((Icon, i) => {
    const label = ICON_SEA_COPY.order[i % ICON_SEA_COPY.order.length]
    return {
      node: (
        <div
          className={styles.cell}
          style={{ animationDelay: `${(i * 0.28).toFixed(2)}s` }} /* 波浪相位：逐项错开 */
        >
          <Icon size={40} />
          <span className={styles.label}>{label}</span>
        </div>
      ),
      ariaLabel: label,
      title: label,
    }
  })

  return (
    <section className={styles.section} aria-label="功能一览">
      <div className={`${styles.head} landing-wrap`}>
        <h2 className={styles.caption}>
          <span>{text.slice(0, youIdx)}</span>
          <span className={styles.you}>{text[youIdx]}</span>
          <span>{text.slice(youIdx + 1)}</span>
        </h2>
      </div>

      <div className={styles.sea}>
        <LogoLoop
          logos={logos}
          speed={reduced ? 0 : 80}
          hoverSpeed={reduced ? 0 : 30}
          direction="left"
          gap={28}
          logoHeight={64}
          /* 纵向留白 = 波浪的行程余量（Skyer 2026-09-25）：LogoLoop 根节点是
             overflow-x-hidden，按规范另一轴计算为 overflow-y auto → 裁剪箱即
             单元格高度，浮动下沉的图标会被裁掉。padding 撑大裁剪箱后 ±16px 全程可见 */
          style={{ paddingBlock: 26 }}
          fadeOut
          fadeOutColor="#10161E"
          ariaLabel={`功能顺序：${ICON_SEA_COPY.order.join('、')}`}
        />
      </div>
    </section>
  )
}

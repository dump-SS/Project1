import { useReducedMotion } from '../../hooks/useReducedMotion'
import { ICON_SEA_COPY } from '../../content/copy'
import { SEA_ICONS } from '../../icons/FeatureIcons'
import styles from './IconSea.module.css'

/**
 * 图标海屏（visual-language §7.7）：功能图标按「学生的一天」顺序
 * 横向无缝循环（×2 复制 + translateX(-50%)）、极慢（~80s）。
 * 配文把中心拉回「你」，否则这屏就变成功能罗列页。
 */
export default function IconSea() {
  const reduced = useReducedMotion()
  const text = ICON_SEA_COPY.caption
  const youIdx = text.indexOf(ICON_SEA_COPY.highlight)
  const doubled = [...SEA_ICONS, ...SEA_ICONS] // 首尾接缝会露馅 → 复制一份无缝循环

  return (
    <section className={styles.section} aria-label="功能一览">
      <div className={`${styles.head} landing-wrap`}>
        <h2 className={styles.caption}>
          <span>{text.slice(0, youIdx)}</span>
          <span className={styles.you}>{text[youIdx]}</span>
          <span>{text.slice(youIdx + 1)}</span>
        </h2>
      </div>

      <div
        className={styles.sea}
        aria-label={`功能顺序：${ICON_SEA_COPY.order.join('、')}`}
      >
        <div className={`${styles.track} ${reduced ? '' : styles.trackAnim}`}>
          {doubled.map((Icon, i) => (
            <div className={styles.cell} key={i} aria-hidden={i >= SEA_ICONS.length}>
              <Icon size={40} />
              <span className={styles.label}>{ICON_SEA_COPY.order[i % SEA_ICONS.length]}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

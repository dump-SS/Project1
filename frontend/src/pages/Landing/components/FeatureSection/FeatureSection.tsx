import DecryptedText from '../bits/DecryptedText'
import TiltedCard from '../bits/TiltedCard'
import { useInView } from '../../hooks/useInView'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { FEATURE_SCREENS } from '../../content/copy'
import { DIALOGUES } from '../../content/dialogues'
import {
  IconStopwatch, IconReportCard, IconNotebook, IconFlask, IconBook,
} from '../../icons/DarkMotifs'
import type { ComponentType, SVGProps } from 'react'
import styles from './FeatureSection.module.css'

/**
 * 功能屏 ×3（visual-language §7.3–7.5 / Skyer 2026-09-25 调整）：
 * 标题 = 该屏对话里产品说过的原句（加「」），入场改 Decrypted Text
 * （滚动到位置由组件内置 IO 触发）；首屏标题按要求在「记住了多少，」后换行；
 * 功能名小字扩写为面向用户的技术说明段。
 * 证据 = 真对话 Tilted Card（1 句用户无衬线 + 2 句产品衬线，只删句不改字）；
 * 每屏蓝色只一处（光晕落在对话卡上）；底部暗纹换主题物件。
 */

/** 每屏暗纹物件（互不雷同，dev-spec §4.3 验收项） */
const SCREEN_META: Record<
  string,
  { motifs: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>[] }
> = {
  state: { motifs: [IconStopwatch, IconReportCard] },
  'error-book': { motifs: [IconNotebook, IconFlask] },
  review: { motifs: [IconBook, IconNotebook] },
}

export default function FeatureSection({ screenId }: { screenId: string }) {
  const reduced = useReducedMotion()
  const screen = FEATURE_SCREENS.find((s) => s.id === screenId)
  const [sectionRef, inView] = useInView<HTMLElement>('0px 0px', true)
  if (!screen) return null

  const meta = SCREEN_META[screenId]
  const dialogue = DIALOGUES[screen.dialogueId]
  /* 标题行：首屏两行断法（Skyer 指定），其余单行 */
  const titleLines: readonly string[] = (screen as { titleLines?: readonly string[] }).titleLines ?? [screen.title]

  return (
    <section
      className={`${styles.section} ${inView ? styles.sectionIn : ''}`}
      ref={sectionRef}
      aria-label={screen.featureName}
    >
      <div className={`${styles.inner} landing-wide`}>
        {/* 左：金句大字标题（对话原句，「」+ Decrypted Text 入场）+ 功能名与说明段 */}
        <div className={styles.left}>
          <h2 className={styles.title} aria-label={screen.title}>
            {titleLines.map((line, i) =>
              reduced ? (
                <span key={i} className={styles.titleLine}>{line}</span>
              ) : (
                <DecryptedText
                  key={i}
                  text={line}
                  animateOn="view"
                  sequential
                  speed={28}
                  maxIterations={14}
                  revealDirection="start"
                  /* parentClassName = 容器级（行块）；className 是字符级，勿在此设 display */
                  parentClassName={styles.titleLine}
                  encryptedClassName={styles.titleEncrypted}
                />
              ),
            )}
          </h2>
          <p className={styles.featureName}>{screen.featureName}</p>
          <p className={styles.description}>{screen.description}</p>
        </div>

      {/* 对话卡片：Tilted Card（2026-09-25 Skyer 指定）——3D 倾斜；
          气泡为前置层（translateZ，随倾斜产生前后景视差），卡面为纯色底 */}
      <div className={styles.dialogueWrap}>
        <TiltedCard
          containerWidth="100%"
          containerHeight="auto"
          imageWidth="auto"
          imageHeight="auto"
          rotateAmplitude={14}
          perspective={1600}
          scaleOnHover={1.02}
          showMobileWarning={false}
          showTooltip={false}
        >
          <div className={styles.cardFace} aria-label="真实对话">
            <div className={styles.bubbleLayer}>
              <div className={styles.bubbleUser}>
                <p className={styles.userText}>{dialogue.user}</p>
              </div>
              {dialogue.product.map((line, i) => (
                <div className={styles.bubbleProduct} key={i}>
                  <p className={styles.productText}>{line}</p>
                </div>
              ))}
            </div>
          </div>
        </TiltedCard>
      </div>
      </div>

      {/* 底部暗纹：换主题物件（近不可见） */}
      <div className={styles.motifStrip} aria-hidden>
        {meta.motifs.map((Icon, i) => (
          <Icon key={i} size={i === 0 ? 44 : 56} className={styles.motifIcon} />
        ))}
      </div>
    </section>
  )
}

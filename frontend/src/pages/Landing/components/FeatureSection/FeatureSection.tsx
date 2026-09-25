import TextType from '../bits/TextType'
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
 * 功能屏 ×3（visual-language §7.3–7.5）：
 * 标题 = 该屏对话里产品说过的原句（加「」+ 逐字「写出」）；
 * 证据 = 真对话（1 句用户无衬线 + 2 句产品衬线，只删句不改字）；
 * 每屏蓝色只一处（光晕落在对话上）；底部暗纹换主题物件。
 * hero 是「删词」、这里是「写出」——一删一写构成呼应，参数刻意不同。
 */

/** 每屏编排参数（互不雷同，dev-spec §4.3 验收项） */
const SCREEN_META: Record<
  string,
  { motifs: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>[]; typing: { speed: number; initialDelay: number; variable?: { min: number; max: number } } }
> = {
  state: {
    motifs: [IconStopwatch, IconReportCard],
    typing: { speed: 90, initialDelay: 300, variable: { min: 60, max: 130 } },
  },
  'error-book': {
    motifs: [IconNotebook, IconFlask],
    typing: { speed: 140, initialDelay: 150 },
  },
  review: {
    motifs: [IconBook, IconNotebook],
    typing: { speed: 70, initialDelay: 450, variable: { min: 40, max: 110 } },
  },
}

export default function FeatureSection({ screenId }: { screenId: string }) {
  const reduced = useReducedMotion()
  const screen = FEATURE_SCREENS.find((s) => s.id === screenId)
  const [sectionRef, inView] = useInView<HTMLElement>('0px 0px', true)
  if (!screen) return null

  const meta = SCREEN_META[screenId]
  const dialogue = DIALOGUES[screen.dialogueId]
  const typing = meta.typing

  return (
    <section
      className={`${styles.section} ${inView ? styles.sectionIn : ''}`}
      ref={sectionRef}
      aria-label={screen.featureName}
    >
      <div className={`${styles.inner} landing-wrap`}>
        {/* 左：金句大字标题（对话原句，加「」逐字打出）+ 功能名小字 */}
        <div className={styles.left}>
          {reduced ? (
            /* reduced-motion：直接显示成稿（dev-spec §6） */
            <h2 className={styles.title}>{screen.title}</h2>
          ) : (
            <h2 className={styles.title}>
              {inView && (
                <TextType
                  text={screen.title}
                  as="span"
                  showCursor={false}
                  typingSpeed={typing.speed}
                  initialDelay={typing.initialDelay}
                  variableSpeed={typing.variable}
                  loop={false}
                  holdOnComplete
                  startOnVisible={false}
                />
              )}
            </h2>
          )}
          <p className={styles.featureName}>{screen.featureName}</p>
        </div>

        {/* 右：对话气泡（光晕落在此处 = 本屏唯一蓝） */}
        <div className={styles.dialogue} aria-label="真实对话">
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

      {/* 底部暗纹：换主题物件（近不可见） */}
      <div className={styles.motifStrip} aria-hidden>
        {meta.motifs.map((Icon, i) => (
          <Icon key={i} size={i === 0 ? 44 : 56} className={styles.motifIcon} />
        ))}
      </div>
    </section>
  )
}

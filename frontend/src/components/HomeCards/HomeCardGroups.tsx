/**
 * 三组卡区的展示层（纯展示，可用 renderToStaticMarkup 在 node 环境单测）。
 * 组顺序按传入顺序渲染（后端已保证 Go on → 推荐 → 洞察）；空组后端不返回，这里也不补。
 * 空态给可点击的对话起点；不新造快捷动作面板——登录态的快捷动作仍在输入框「+」菜单（charter §四/§五）。
 */
import styles from './index.module.css'
import HomeCardView from './HomeCardView'
import type { ShownReporter } from './impressionReporter'
import {
  HOME_CARD_GROUP_LABEL,
  type HomeCard,
  type HomeCardGroup,
  type HomeCardGroupResult,
} from '@/services/homeCards'

/** 空态的可点击对话起点（不是数据、不是承诺，只是把用户送进对话） */
export const EMPTY_STARTERS = [
  '帮我看看今天先学什么',
  '复盘我上一次学习',
  '把本周目标拆成小步',
]

interface HomeCardGroupsProps {
  groups: HomeCardGroupResult[]
  reporter: ShownReporter
  onCardClick: (card: HomeCard, group: HomeCardGroup) => void
  onDismiss: (card: HomeCard, group: HomeCardGroup) => void
  onStarter: (text: string) => void
}

export default function HomeCardGroups({
  groups,
  reporter,
  onCardClick,
  onDismiss,
  onStarter,
}: HomeCardGroupsProps) {
  if (groups.length === 0) {
    return (
      <div className={styles.empty}>
        <h2 className={styles.emptyTitle}>今天还没有推荐卡</h2>
        <p className={styles.emptyText}>
          记录几次学习、或完成一次状态评估后，这里会按「Go on → 推荐 → 洞察」给你克制的建议。
          现在也可以直接开始一段对话：
        </p>
        <div className={styles.starters}>
          {EMPTY_STARTERS.map((text) => (
            <button key={text} type="button" className={styles.starter} onClick={() => onStarter(text)}>
              {text}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
      {groups.map((g) => (
        <section key={g.group} className={styles.group} aria-label={HOME_CARD_GROUP_LABEL[g.group]}>
          <h2 className={styles.groupTitle}>{HOME_CARD_GROUP_LABEL[g.group]}</h2>
          <div className={styles.row}>
            {g.cards.map((card) => (
              <HomeCardView
                key={`${g.group}:${card.fingerprint}`}
                card={card}
                group={g.group}
                reporter={reporter}
                onCardClick={onCardClick}
                onDismiss={onDismiss}
              />
            ))}
          </div>
        </section>
      ))}
    </>
  )
}

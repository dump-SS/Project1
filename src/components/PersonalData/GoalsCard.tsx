/**
 * 模块⑥ 短/长期目标及历史完成情况：分「进行中」与「已完成」两区，卡片式陈列。
 */

import SectionCard from './SectionCard';
import styles from './GoalsCard.module.css';
import { fetchGoals, placeholderGoals } from '@/services/goals';
import { usePanelData } from '@/hooks/usePanelData';
import { dayjs } from '@/utils/aggregate';
import type { GoalCard as GoalCardModel } from '@/types/view';

function formatTargetDate(targetDate: string | null): string {
  if (!targetDate) return '未设截止日期';
  const date = dayjs(targetDate);
  const diffDays = date.startOf('day').diff(dayjs().startOf('day'), 'day');

  if (diffDays > 0) return `${date.format('M 月 D 日')} · 还剩 ${diffDays} 天`;
  if (diffDays === 0) return `${date.format('M 月 D 日')} · 就是今天`;
  return date.format('M 月 D 日');
}

function GoalItem({ goal }: { goal: GoalCardModel }) {
  const isFinished = goal.status === 'archived';

  return (
    <li className={[styles.goal, isFinished ? styles.goalFinished : ''].filter(Boolean).join(' ')}>
      <div className={styles.goalHead}>
        <h3 className={styles.goalTitle}>{goal.title}</h3>
        <span
          className={[
            styles.badge,
            goal.type === 'short_term' ? styles.badgeShort : styles.badgeLong,
          ].join(' ')}
        >
          {goal.typeLabel}
        </span>
      </div>

      <div className={styles.goalMeta}>
        <span>{goal.subjectLabel}</span>
        <span className={styles.metaDivider} />
        <span>{formatTargetDate(goal.targetDate)}</span>
        <span className={styles.metaDivider} />
        <span className={isFinished ? styles.statusFinished : styles.statusActive}>
          {goal.statusLabel}
        </span>
      </div>

      <div className={styles.progressRow}>
        <div className={styles.progressTrack}>
          <div
            className={[styles.progressFill, isFinished ? styles.progressFillDone : '']
              .filter(Boolean)
              .join(' ')}
            style={{ width: `${goal.percent}%` }}
          />
        </div>
        <span className={styles.progressText}>{goal.percent}%</span>
      </div>

      <div className={styles.goalTasks}>
        已完成 {goal.completedTasks} / {goal.plannedTasks} 个任务
      </div>

      {isFinished ? (
        goal.completionNote ? (
          <p className={styles.completionNote}>{goal.completionNote}</p>
        ) : (
          <p className={styles.completionPending}>完成总结待生成 —— 接口暂无对应字段</p>
        )
      ) : null}
    </li>
  );
}

function GoalsCard() {
  const { data, loading, source, error } = usePanelData(fetchGoals, placeholderGoals());

  return (
    <SectionCard
      index="⑥"
      title="目标"
      subtitle="正在走的路与走过的路"
      source={source}
      error={error}
      loading={loading}
    >
      <div className={styles.group}>
        <h3 className={styles.groupTitle}>
          进行中
          <span className={styles.groupCount}>{data.active.length}</span>
        </h3>

        {data.active.length === 0 ? (
          <p className={styles.empty}>还没有正在进行的目标，先给自己定一个小的吧。</p>
        ) : (
          <ul className={styles.list}>
            {data.active.map((goal) => (
              <GoalItem key={goal.goalId} goal={goal} />
            ))}
          </ul>
        )}
      </div>

      <div className={styles.group}>
        <h3 className={styles.groupTitle}>
          已完成
          <span className={styles.groupCount}>{data.finished.length}</span>
        </h3>

        {data.finished.length === 0 ? (
          <p className={styles.empty}>历史还很空，慢慢来。</p>
        ) : (
          <ul className={styles.list}>
            {data.finished.map((goal) => (
              <GoalItem key={goal.goalId} goal={goal} />
            ))}
          </ul>
        )}
      </div>

      <p className={styles.poem}>走过的路都算数，未竟的也不必着急。</p>
    </SectionCard>
  );
}

export default GoalsCard;

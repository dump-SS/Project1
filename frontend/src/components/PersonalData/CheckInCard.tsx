/**
 * 模块① 学习情况（日常打卡）及总结：7 格打卡行，点击展开当天总结。
 */

import { useState } from 'react';
import SectionCard from './SectionCard';
import styles from './CheckInCard.module.css';
import { fetchCheckIn, placeholderCheckIn } from '@/services/checkIn';
import { usePanelData } from '@/hooks/usePanelData';
import { subjectLabels } from '@/styles/theme';
import { formatDuration } from '@/utils/aggregate';
import type { CheckInDay } from '@/types/view';

function DayDetail({ day }: { day: CheckInDay }) {
  if (!day.checked) {
    return (
      <div className={styles.detail}>
        <p className={styles.detailEmpty}>这一天没有留下记录，空白也是节奏的一部分。</p>
      </div>
    );
  }

  return (
    <div className={styles.detail}>
      <div className={styles.detailMeta}>
        <span className={styles.detailDate}>{day.dayLabel}</span>
        <span className={styles.detailDivider} />
        <span>{formatDuration(day.totalMinutes)}</span>
        <span className={styles.detailDivider} />
        <span>
          {day.subjects.length > 0
            ? day.subjects.map((subject) => subjectLabels[subject]).join(' · ')
            : '未记录学科'}
        </span>
      </div>

      {day.summary ? (
        <p className={styles.detailSummary}>{day.summary}</p>
      ) : (
        <p className={styles.detailPending}>
          当日一句话总结待生成 —— 接口暂未提供单日总结能力
        </p>
      )}
    </div>
  );
}

function CheckInCard() {
  const { data, loading, source, error } = usePanelData(fetchCheckIn, placeholderCheckIn());
  const [activeDate, setActiveDate] = useState<string | null>(null);

  const activeDay = data.days.find((day) => day.date === activeDate) ?? null;

  return (
    <SectionCard
      index="①"
      title="学习情况"
      subtitle="最近七日的痕迹"
      source={source}
      error={error}
      loading={loading}
    >
      <div className={styles.row}>
        {data.days.map((day) => {
          const isActive = day.date === activeDate;
          return (
            <button
              key={day.date}
              type="button"
              className={[
                styles.cell,
                day.checked ? styles.cellChecked : styles.cellEmpty,
                isActive ? styles.cellActive : '',
                day.isToday ? styles.cellToday : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => setActiveDate(isActive ? null : day.date)}
              aria-pressed={isActive}
              aria-label={`${day.dayLabel} ${day.checked ? '已打卡' : '未打卡'}`}
            >
              <span className={styles.weekday}>{day.weekdayLabel}</span>
              <span className={styles.dot} />
              <span className={styles.date}>{day.dayLabel}</span>
            </button>
          );
        })}
      </div>

      {activeDay ? <DayDetail day={activeDay} /> : null}

      <p className={styles.footer}>
        本周已打卡 {data.checkedCount}/{data.totalDays} 天，继续保持 🌿
      </p>
    </SectionCard>
  );
}

export default CheckInCard;

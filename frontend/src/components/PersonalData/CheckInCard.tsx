/**
 * 模块① 学习情况（日常打卡）及总结：7 格打卡行，点击展开当天总结。
 *
 * 总结按需懒加载：仅在用户点击有打卡的日期时才请求 /daily-summary，
 * 避免进入页面就发起 1-7 次 LLM 调用阻塞首屏。
 */

import { useEffect, useState } from 'react';
import SectionCard from './SectionCard';
import styles from './CheckInCard.module.css';
import { fetchCheckIn, fetchDaySummary, placeholderCheckIn } from '@/services/checkIn';
import { usePanelData } from '@/hooks/usePanelData';
import { subjectLabels } from '@/styles/theme';
import { formatDuration } from '@/utils/aggregate';
import type { CheckInDay } from '@/types/view';

function DayDetail({
  day,
  summary,
  summaryLoading,
  summaryError,
  onRetrySummary,
}: {
  day: CheckInDay;
  summary: string | null;
  summaryLoading: boolean;
  summaryError: boolean;
  onRetrySummary: () => void;
}) {
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

      {summaryLoading ? (
        <p className={styles.detailPending}>正在生成今日总结…</p>
      ) : summaryError ? (
        <p className={styles.detailPending}>
          今日总结生成失败
          <button type="button" className={styles.detailRetry} onClick={onRetrySummary}>
            重试
          </button>
        </p>
      ) : summary ? (
        <p className={styles.detailSummary}>{summary}</p>
      ) : (
        <p className={styles.detailPending}>今日总结待生成</p>
      )}
    </div>
  );
}

function CheckInCard() {
  const { data, loading, source, error } = usePanelData(fetchCheckIn, placeholderCheckIn(), 'check-in');
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(false);

  const activeDay = data.days.find((day) => day.date === activeDate) ?? null;

  // 展开日期时懒加载总结
  useEffect(() => {
    if (!activeDay || !activeDay.checked) {
      setSummary(null);
      setSummaryLoading(false);
      setSummaryError(false);
      return;
    }
    let cancelled = false;
    setSummaryLoading(true);
    setSummaryError(false);
    setSummary(null);
    fetchDaySummary(activeDay.date)
      .then((text) => {
        if (cancelled) return;
        setSummary(text || null);
        setSummaryLoading(false);
        if (!text) setSummaryError(true);
      })
      .catch(() => {
        if (cancelled) return;
        setSummaryLoading(false);
        setSummaryError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [activeDay?.date, activeDay?.checked]);

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

      {activeDay ? (
        <DayDetail
          day={activeDay}
          summary={summary}
          summaryLoading={summaryLoading}
          summaryError={summaryError}
          onRetrySummary={() => {
            // 触发 useEffect 重跑：把 activeDate 设为 null 再设回去
            const cur = activeDay.date;
            setActiveDate(null);
            setTimeout(() => setActiveDate(cur), 0);
          }}
        />
      ) : null}

      <p className={styles.footer}>
        本周已打卡 {data.checkedCount}/{data.totalDays} 天，继续保持 🌿
      </p>
    </SectionCard>
  );
}

export default CheckInCard;

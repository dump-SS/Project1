/**
 * 模块⑤ 内置日历：有学习记录的日期打蓝点，点击日期在右侧展示当天数据摘要。
 */

import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Calendar } from 'antd';
import type { Dayjs } from 'dayjs';
import SectionCard from './SectionCard';
import styles from './CalendarCard.module.css';
import { fetchCalendar, placeholderCalendar } from '@/services/calendar';
import { usePanelData } from '@/hooks/usePanelData';
import { subjectColors, stateLabelColors, stateLabels } from '@/styles/theme';
import { DATE_FORMAT, dayjs, formatDuration } from '@/utils/aggregate';
import type { CalendarDayDetail } from '@/types/view';

function DayDetailPanel({ date, detail }: { date: Dayjs; detail: CalendarDayDetail | undefined }) {
  return (
    <aside className={styles.detail}>
      <div className={styles.detailHeader}>
        <span className={styles.detailDate}>{date.format('M 月 D 日')}</span>
        <span className={styles.detailWeekday}>{date.format('dddd')}</span>
      </div>

      {!detail ? (
        <p className={styles.detailEmpty}>这一天还是空的，留白也无妨。</p>
      ) : (
        <>
          <div className={styles.detailMetrics}>
            <div className={styles.detailMetric}>
              <span className={styles.detailMetricValue}>
                {formatDuration(detail.totalMinutes)}
              </span>
              <span className={styles.detailMetricLabel}>学习时长</span>
            </div>
            <div className={styles.detailMetric}>
              <span className={styles.detailMetricValue}>
                {detail.focusAvg === null ? '—' : detail.focusAvg.toFixed(1)}
              </span>
              <span className={styles.detailMetricLabel}>专注度</span>
            </div>
            <div className={styles.detailMetric}>
              <span className={styles.detailMetricValue}>
                {detail.fatigueAvg === null ? '—' : detail.fatigueAvg.toFixed(1)}
              </span>
              <span className={styles.detailMetricLabel}>疲劳度</span>
            </div>
          </div>

          <ul className={styles.detailSubjects}>
            {detail.subjects.map((item) => (
              <li key={item.subject} className={styles.detailSubject}>
                <span
                  className={styles.detailSubjectDot}
                  style={{ background: subjectColors[item.subject] }}
                />
                <span className={styles.detailSubjectName}>{item.label}</span>
                <span className={styles.detailSubjectMinutes}>{formatDuration(item.minutes)}</span>
                {item.stateLabel ? (
                  <span
                    className={styles.detailStateTag}
                    style={{
                      color: stateLabelColors[item.stateLabel],
                      borderColor: stateLabelColors[item.stateLabel],
                    }}
                  >
                    {stateLabels[item.stateLabel]}
                  </span>
                ) : (
                  <span className={styles.detailStateTagEmpty}>—</span>
                )}
              </li>
            ))}
          </ul>

          <p className={styles.detailPending}>状态标签按学科分别给出，不做跨学科合并</p>
        </>
      )}
    </aside>
  );
}

function CalendarCard() {
  const [month, setMonth] = useState(() => dayjs().format('YYYY-MM'));
  const [selectedDate, setSelectedDate] = useState<Dayjs>(() => dayjs());

  const fetcher = useCallback((signal: AbortSignal) => fetchCalendar(month, signal), [month]);

  const { data, loading, source, error } = usePanelData(fetcher, placeholderCalendar(month), [
    month,
  ]);

  const selectedDetail = useMemo(
    () => data.marks[selectedDate.format(DATE_FORMAT)],
    [data.marks, selectedDate],
  );

  const handleSelect = useCallback((value: Dayjs, info: { source: string }) => {
    // 点击月份/年份切换器时也会触发 onSelect，只响应真正的日期点击
    if (info.source === 'date') {
      setSelectedDate(value);
    }
    setMonth(value.format('YYYY-MM'));
  }, []);

  const fullCellRender = useCallback(
    (current: Dayjs, info: { type: string; originNode: ReactNode }) => {
      if (info.type !== 'date') return info.originNode;

      const key = current.format(DATE_FORMAT);
      const detail = data.marks[key];
      const isSelected = current.isSame(selectedDate, 'day');
      const inMonth = current.format('YYYY-MM') === month;

      return (
        <div
          className={[
            styles.cell,
            isSelected ? styles.cellSelected : '',
            inMonth ? '' : styles.cellOutside,
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className={styles.cellDate}>{current.date()}</span>
          <span className={detail ? styles.cellDot : styles.cellDotPlaceholder} />
        </div>
      );
    },
    [data.marks, selectedDate, month],
  );

  return (
    <SectionCard
      index="⑤"
      title="学习日历"
      subtitle="点亮的日子"
      source={source}
      error={error}
      loading={loading}
    >
      <div className={styles.layout}>
        <div className={styles.calendar}>
          <Calendar
            fullscreen={false}
            value={selectedDate}
            onSelect={handleSelect}
            onPanelChange={(value) => setMonth(value.format('YYYY-MM'))}
            fullCellRender={fullCellRender}
          />
        </div>

        <DayDetailPanel date={selectedDate} detail={selectedDetail} />
      </div>
    </SectionCard>
  );
}

export default CalendarCard;

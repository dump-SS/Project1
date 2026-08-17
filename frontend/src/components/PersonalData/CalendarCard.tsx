/**
 * 模块⑤ 内置日历：有学习记录的日期打蓝点，点击日期在右侧展示当天数据摘要。
 *
 * 当日面板可对单条学习记录执行删除（PRD 5.2 边界场景「记录删除回溯」）：
 * - 二次确认：避免误删
 * - 删除成功后调用 usePanelData 的 reload 重拉当月数据
 * - 服务端在 DELETE 响应里同步返回 recalculatedAssessment，
 *   本期暂不消费该结果（仅刷新列表），后续若要做"局部更新学科标签"可在此接住
 */

import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Calendar, Modal } from 'antd';
import type { Dayjs } from 'dayjs';
import SectionCard from './SectionCard';
import styles from './CalendarCard.module.css';
import { fetchCalendar, placeholderCalendar } from '@/services/calendar';
import { deleteLearningRecord } from '@/services/learningRecord';
import { usePanelData } from '@/hooks/usePanelData';
import { isNetworkError } from '@/services/http';
import { subjectColors, stateLabelColors, stateLabels, subjectLabels } from '@/styles/theme';
import { DATE_FORMAT, dayjs, formatDuration } from '@/utils/aggregate';
import type { CalendarDayDetail } from '@/types/view';
import type { LearningRecord } from '@/types/api';

function formatStartTime(iso: string): string {
  return dayjs(iso).format('HH:mm');
}

function describeRecord(record: LearningRecord): string {
  const subject = subjectLabels[record.subject] ?? record.subject;
  return `${subject} · ${formatDuration(record.durationMinutes)} · 专注 ${record.selfReport.focus}/5 · 疲劳 ${record.selfReport.fatigue}/5`;
}

function DayDetailPanel({
  date,
  detail,
  onRequestDelete,
}: {
  date: Dayjs;
  detail: CalendarDayDetail | undefined;
  onRequestDelete: (record: LearningRecord) => void;
}) {
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

          {detail.records && detail.records.length > 0 ? (
            <div className={styles.recordsSection}>
              <h4 className={styles.recordsTitle}>当天记录</h4>
              <ul className={styles.recordsList}>
                {detail.records.map((record) => (
                  <li key={record.recordId} className={styles.recordItem}>
                    <div className={styles.recordMeta}>
                      <span className={styles.recordTime}>
                        {formatStartTime(record.startedAt)}
                      </span>
                      <span className={styles.recordDesc}>{describeRecord(record)}</span>
                    </div>
                    <button
                      type="button"
                      className={styles.recordDelete}
                      onClick={() => onRequestDelete(record)}
                      aria-label={`删除 ${formatStartTime(record.startedAt)} 的记录`}
                    >
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

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

  const { data, loading, source, error, reload } = usePanelData(
    fetcher,
    placeholderCalendar(month),
    'calendar',
    [month],
  );

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

  /** 待删除记录的二次确认：Modal.confirm 提供 onOk/onCancel，比手写 modal 简单 */
  const [deleting, setDeleting] = useState<LearningRecord | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleRequestDelete = useCallback((record: LearningRecord) => {
    setDeleting(record);
    setDeleteError(null);
  }, []);

  const handleCancelDelete = useCallback(() => {
    if (deletingBusy) return;
    setDeleting(null);
    setDeleteError(null);
  }, [deletingBusy]);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleting) return;
    setDeletingBusy(true);
    setDeleteError(null);
    try {
      await deleteLearningRecord(deleting.recordId);
      setDeleting(null);
      reload();
    } catch (err) {
      const message = err instanceof Error ? err.message : null;
      setDeleteError(
        isNetworkError(err) ? '后端暂不可用，请稍后再试' : (message ?? '删除失败，请稍后再试'),
      );
    } finally {
      setDeletingBusy(false);
    }
  }, [deleting, reload]);

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

  const confirmSubject =
    deleting ? (subjectLabels[deleting.subject] ?? deleting.subject) : '';

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

        <DayDetailPanel
          date={selectedDate}
          detail={selectedDetail}
          onRequestDelete={handleRequestDelete}
        />
      </div>

      <Modal
        open={!!deleting}
        title="删除这条学习记录？"
        okText="确认删除"
        cancelText="再想想"
        okButtonProps={{ danger: true, loading: deletingBusy }}
        cancelButtonProps={{ disabled: deletingBusy }}
        onOk={handleConfirmDelete}
        onCancel={handleCancelDelete}
        destroyOnClose
      >
        {deleting ? (
          <div>
            <p>
              将删除 <b>{confirmSubject}</b> · {formatDuration(deleting.durationMinutes)} 的记录
              （{formatStartTime(deleting.startedAt)} 开始）。
            </p>
            <p style={{ marginTop: 8, color: '#8ca3b5', fontSize: 12 }}>
              删除后服务端会立即重算当前窗口的状态分。记录本身不可恢复，请确认。
            </p>
            {deleteError ? (
              <p style={{ marginTop: 8, color: '#b43232' }}>{deleteError}</p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </SectionCard>
  );
}

export default CalendarCard;

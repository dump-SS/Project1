/**
 * 模块⑦ 学习复盘：最新一期复盘内容 + 反馈按钮。
 */

import { useState, useEffect, useCallback } from 'react';
import SectionCard from './SectionCard';
import { fetchLatestSummary } from '@/services/summaries';
import { putSummaryFeedback } from '@/services/feedback';
import type { Summary } from '@/types/api';
import type { DataSource } from '@/types/view';
import styles from './SummaryCard.module.css';

const RATING_LABELS: Record<string, string> = {
  useful: '有用',
  neutral: '一般',
  not_useful: '没用',
};

function SummaryFeedback({ summary }: { summary: Summary }) {
  const [rating, setRating] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existingFeedback = summary.feedback;
  const showButtons = !existingFeedback && !sent;

  const handleFeedback = useCallback(
    async (r: string) => {
      setRating(r);
      setError(null);
      try {
        await putSummaryFeedback(summary.summaryId, r as 'useful' | 'neutral' | 'not_useful');
        setSent(true);
      } catch {
        setError('反馈提交失败');
        setRating(null);
      }
    },
    [summary.summaryId],
  );

  return (
    <div className={styles.feedback}>
      <span className={styles.feedbackLabel}>
        {existingFeedback
          ? '已收到你的评价'
          : sent
            ? '感谢反馈'
            : '这篇复盘对你有帮助吗？'}
      </span>
      {showButtons && (
        <div className={styles.feedbackRow}>
          {['useful', 'neutral', 'not_useful'].map((r) => (
            <button
              key={r}
              type="button"
              className={[styles.feedbackBtn, rating === r ? styles.feedbackBtnActive : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => handleFeedback(r)}
            >
              {RATING_LABELS[r]}
            </button>
          ))}
        </div>
      )}
      {error && <span className={styles.feedbackError}>{error}</span>}
    </div>
  );
}

function SummaryCard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<DataSource>('placeholder');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    setLoading(true);
    fetchLatestSummary(controller.signal)
      .then((result) => {
        if (cancelled) return;
        if (result) {
          setSummary(result);
          setSource('api');
        } else {
          setSummary(null);
          setSource('api');
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : '获取复盘失败');
        setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const content = summary?.content;
  const dataPoints = summary?.dataPoints;
  // 复盘生成时记录的「今日已完成 N / M」快照（PRD 5.4）
  const planCompleted = dataPoints?.planCompletedCount;
  const planTotal = dataPoints?.planTotalCount;

  return (
    <SectionCard
      index="⑦"
      title="学习复盘"
      subtitle={content ? `${summary?.periodStart ?? '?'} - ${summary?.periodEnd ?? '?'}` : '暂无复盘'}
      source={source}
      error={error}
      loading={loading}
    >
      {content ? (
        <div className={styles.body}>
          {/* 累计完成计数（PRD 5.4） */}
          {planTotal != null && planTotal > 0 && (
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>复盘时累计完成</span>
              <strong className={styles.metaValue}>
                {planCompleted ?? 0} / {planTotal}
              </strong>
              <span className={styles.metaHint}>个计划任务</span>
            </div>
          )}

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>总览</h3>
            <p className={styles.text}>{content.overview}</p>
          </div>

          {content.patterns.length > 0 && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>发现的规律</h3>
              <ul className={styles.list}>
                {content.patterns.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
          )}

          {content.suggestions.length > 0 && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>建议</h3>
              <ul className={styles.list}>
                {content.suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>寄语</h3>
            <p className={styles.text}>{content.encouragement}</p>
          </div>

          <SummaryFeedback summary={summary} />
        </div>
      ) : (
        <p className={styles.empty}>
          还没有生成复盘。完成几次学习记录后，系统会自动为你生成。
        </p>
      )}
    </SectionCard>
  );
}

export default SummaryCard;
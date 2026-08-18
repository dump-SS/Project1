/**
 * 模块⑧ AI 调权后的算法计算结果。
 *
 * 展示 7 天窗口内、按当前权重（UserWeightConfig，AI 调权后）算出的：
 * - 窗口分（α × 行为子分均值 + β × 自评子分均值）
 * - 行为子分均值 / 自评子分均值
 * - 各自加权后贡献 + 占比
 * - 当前权重快照（α / β + w1-w6）
 * - 状态标签 + 趋势 + 信号
 *
 * 让用户直观感受"调权改了 α/β → 状态分怎么变"。
 */

import { useEffect, useState } from 'react';
import SectionCard from './SectionCard';
import styles from './StateBreakdownCard.module.css';
import { fetchStateBreakdown, type StateBreakdown as StateBreakdownData } from '@/services/stateBreakdown';
import { subjectLabels } from '@/styles/theme';

const LABEL_TEXT: Record<string, string> = {
  efficient_stable: '高效稳定',
  fatigue_warning: '疲劳提醒',
  emotion_blocked: '情绪受阻',
  fluctuating_up: '波动上升',
  insufficient_data: '数据不足',
};

const TREND_TEXT: Record<string, string> = {
  up: '上升',
  flat: '平稳',
  down: '下降',
};

const SUBJECT_NAME: Record<string, string> = subjectLabels as Record<string, string>;

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function scoreBar(value: number | null): number {
  if (value == null) return 0;
  return Math.max(0, Math.min(100, value * 100));
}

function StateBreakdownCard() {
  const [data, setData] = useState<StateBreakdownData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchStateBreakdown()
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const subjectName = data ? SUBJECT_NAME[data.subject] ?? data.subject : '';

  return (
    <SectionCard
      index="⑧"
      title="AI 调权后的算法结果"
      subtitle={
        data
          ? `${subjectName} · ${data.recordCount} 条记录 · 7 天窗口`
          : '按当前权重实时计算的状态分与子分贡献'
      }
      source="api"
      error={error}
      loading={loading}
    >
      {data && (
        <>
          {/* 顶部：当前窗口分 */}
          <div className={styles.scoreRow}>
            <div className={styles.scoreBlock}>
              <div className={styles.scoreLabel}>当前状态分</div>
              <div className={styles.scoreValue}>
                {data.windowScore == null ? '—' : data.windowScore.toFixed(3)}
                {data.windowScore != null && <span className={styles.scoreMax}>/1.0</span>}
              </div>
              <div className={styles.labelTag}>
                {LABEL_TEXT[data.stateLabel ?? 'insufficient_data'] ?? data.stateLabel}
                {data.trend && (
                  <span className={styles.trendInline}>
                    {' · 趋势 '}
                    {TREND_TEXT[data.trend] ?? data.trend}
                  </span>
                )}
              </div>
            </div>
            <div className={styles.scoreBar}>
              <div
                className={styles.scoreBarFill}
                style={{ width: `${scoreBar(data.windowScore)}%` }}
              />
            </div>
          </div>

          {/* 子分贡献条 */}
          <div className={styles.contribSection}>
            <div className={styles.contribTitle}>子分加权后贡献</div>
            <div className={styles.contribBar}>
              <div
                className={styles.contribSegBehavior}
                style={{ width: `${data.behaviorShare * 100}%` }}
                title={`行为子分贡献 ${pct(data.behaviorShare)}`}
              />
              <div
                className={styles.contribSegSelf}
                style={{ width: `${data.selfReportShare * 100}%` }}
                title={`自评子分贡献 ${pct(data.selfReportShare)}`}
              />
            </div>
            <div className={styles.contribLegend}>
              <div className={styles.legendItem}>
                <span className={`${styles.legendDot} ${styles.dotBehavior}`} />
                <span className={styles.legendLabel}>行为子分</span>
                <span className={styles.legendValue}>
                  α={data.weights.alpha.toFixed(2)} · 均值 {data.behaviorSubAvg.toFixed(3)} ·{' '}
                  <strong>贡献 {pct(data.behaviorShare)}</strong>
                </span>
              </div>
              <div className={styles.legendItem}>
                <span className={`${styles.legendDot} ${styles.dotSelf}`} />
                <span className={styles.legendLabel}>自评子分</span>
                <span className={styles.legendValue}>
                  β={data.weights.beta.toFixed(2)} · 均值 {data.selfReportSubAvg.toFixed(3)} ·{' '}
                  <strong>贡献 {pct(data.selfReportShare)}</strong>
                </span>
              </div>
            </div>
          </div>

          {/* 权重快照 */}
          <div className={styles.weightSection}>
            <div className={styles.contribTitle}>当前权重（点击「立即调权」会更新）</div>
            <div className={styles.weightGrid}>
              <WeightChip label="α 行为主权重" value={data.weights.alpha} accent="behavior" />
              <WeightChip label="β 自评主权重" value={data.weights.beta} accent="self" />
              <WeightChip label="w1 完成度" value={data.weights.w1} />
              <WeightChip label="w2 正确率" value={data.weights.w2} />
              <WeightChip label="w3 节奏稳定度" value={data.weights.w3} />
              <WeightChip label="w4 专注度" value={data.weights.w4} />
              <WeightChip label="w5 反向疲劳" value={data.weights.w5} />
              <WeightChip label="w6 情绪正向" value={data.weights.w6} />
            </div>
          </div>

          {/* 信号 */}
          {data.signals.length > 0 && (
            <ul className={styles.signalList}>
              {data.signals.map((s, idx) => (
                <li key={idx} className={styles.signalItem}>{s}</li>
              ))}
            </ul>
          )}

          <p className={styles.formulaHint}>
            公式：总分 = α × 行为子分均值 + β × 自评子分均值；α/β 由 AI 在受限区间内按你近期状态调权。
          </p>
        </>
      )}
    </SectionCard>
  );
}

function WeightChip({ label, value, accent }: { label: string; value: number; accent?: 'behavior' | 'self' }) {
  return (
    <div
      className={[
        styles.weightChip,
        accent === 'behavior' ? styles.weightChipBehavior : '',
        accent === 'self' ? styles.weightChipSelf : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className={styles.weightLabel}>{label}</span>
      <span className={styles.weightValue}>{value.toFixed(3)}</span>
    </div>
  );
}

export default StateBreakdownCard;

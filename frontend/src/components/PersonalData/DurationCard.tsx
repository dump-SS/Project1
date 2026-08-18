/**
 * 模块② 学习时长：今日大数字 + 目标进度条 + 最近 7 天趋势面积图。
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import SectionCard from './SectionCard';
import styles from './DurationCard.module.css';
import { fetchDuration, placeholderDuration } from '@/services/duration';
import { usePanelData } from '@/hooks/usePanelData';
import { colors } from '@/styles/theme';
import { toHours } from '@/utils/aggregate';

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipDate}>{label}</div>
      <div className={styles.tooltipValue}>{payload[0]?.value ?? 0} 小时</div>
    </div>
  );
}

function DurationCard() {
  const { data, loading, source, error } = usePanelData(fetchDuration, placeholderDuration(), 'duration');

  const todayHours = toHours(data.todayMinutes);
  const percent =
    data.targetMinutes && data.targetMinutes > 0
      ? Math.min(100, Math.round((data.todayMinutes / data.targetMinutes) * 100))
      : null;

  // 大数字：≥1h 用 "X.Xh" 浮点小时数；<1h 用 "X 分钟" 整数显示，
  // 避免 0.07h 被四舍五入到 0.1h（≈6 分钟）让用户感觉比实际多。
  const todayPrimary =
    data.todayMinutes >= 60
      ? { value: todayHours.toFixed(1), unit: 'h' }
      : { value: Math.round(data.todayMinutes).toString(), unit: 'min' };

  return (
    <SectionCard
      index="②"
      title="学习时长"
      subtitle="今日与近七日"
      source={source}
      error={error}
      loading={loading}
    >
      <div className={styles.metricRow}>
        <div className={styles.metricBlock}>
          <div className={styles.metricLabel}>今日累计</div>
          <div className={styles.metricValue}>
            {todayPrimary.value}
            <span className={styles.metricUnit}>{todayPrimary.unit}</span>
          </div>
        </div>

        <div className={styles.progressBlock}>
          {percent === null ? (
            <p className={styles.noTarget}>今日尚未生成学习计划，暂无目标时长可对比</p>
          ) : (
            <>
              <div className={styles.progressMeta}>
                <span className={styles.progressPercent}>{percent}%</span>
              </div>
              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: `${percent}%` }} />
              </div>
            </>
          )}
        </div>
      </div>

      <div className={styles.chart}>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="durationFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors.primary} stopOpacity={0.28} />
                <stop offset="100%" stopColor={colors.primary} stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid stroke={colors.divider} strokeDasharray="4 4" vertical={false} />
            <XAxis
              dataKey="dayLabel"
              tickLine={false}
              axisLine={false}
              tick={{ fill: colors.textSecondary, fontSize: 12, fontWeight: 300 }}
              dy={8}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: colors.textSecondary, fontSize: 12, fontWeight: 300 }}
              width={48}
              unit="h"
            />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: colors.primarySoft }} />
            <Area
              type="monotone"
              dataKey="hours"
              stroke={colors.primary}
              strokeWidth={2}
              fill="url(#durationFill)"
              dot={{ r: 3, fill: '#ffffff', stroke: colors.primary, strokeWidth: 2 }}
              activeDot={{ r: 5, fill: colors.primary, stroke: '#ffffff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className={styles.poem}>时光不语，落笔即是回答。</p>
    </SectionCard>
  );
}

export default DurationCard;

/**
 * 模块④ 专注程度：日/周/月 Tab 切换，面积图 + 平均分仪表盘 + 文艺风评语。
 */

import { useCallback, useState } from 'react';
import { Tabs } from 'antd';
import {
  Area,
  AreaChart,
  CartesianGrid,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import SectionCard from './SectionCard';
import styles from './FocusCard.module.css';
import { fetchFocus, placeholderFocus } from '@/services/focus';
import { usePanelData } from '@/hooks/usePanelData';
import { colors } from '@/styles/theme';
import type { FocusRange } from '@/types/view';

const RANGE_TABS: Array<{ key: FocusRange; label: string }> = [
  { key: 'day', label: '日' },
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
];

const RANGE_TEXT: Record<FocusRange, string> = {
  day: '今日',
  week: '本周',
  month: '近一月',
};

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | null }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const value = payload[0]?.value;

  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipLabel}>{label}</div>
      <div className={styles.tooltipValue}>
        {value === null || value === undefined ? '无记录' : `${value} / 5.0`}
      </div>
    </div>
  );
}

/** 平均分仪表盘。用 RadialBarChart 拼一个 240° 的半环，避免为一个表盘再引一个图表库 */
function FocusGauge({ average }: { average: number | null }) {
  const value = average ?? 0;
  const gaugeColor = value >= 4 ? colors.success : value >= 3 ? colors.primary : colors.warning;

  return (
    <div className={styles.gauge}>
      <ResponsiveContainer width="100%" height={160}>
        <RadialBarChart
          innerRadius="72%"
          outerRadius="100%"
          startAngle={210}
          endAngle={-30}
          data={[{ name: 'focus', value }]}
        >
          <PolarAngleAxis type="number" domain={[0, 5]} angleAxisId={0} tick={false} />
          <RadialBar
            dataKey="value"
            angleAxisId={0}
            background={{ fill: '#eef7fd' }}
            cornerRadius={999}
            fill={gaugeColor}
          />
        </RadialBarChart>
      </ResponsiveContainer>

      <div className={styles.gaugeCenter}>
        <div className={styles.gaugeValue} style={{ color: gaugeColor }}>
          {average === null ? '—' : average.toFixed(1)}
        </div>
        <div className={styles.gaugeMax}>/ 5.0</div>
      </div>
    </div>
  );
}

function FocusCard() {
  const [range, setRange] = useState<FocusRange>('week');

  const fetcher = useCallback((signal: AbortSignal) => fetchFocus(range, signal), [range]);

  const { data, loading, source, error } = usePanelData(fetcher, placeholderFocus(range), [range]);

  return (
    <SectionCard
      index="④"
      title="专注程度"
      subtitle="自评 1-5 分"
      source={source}
      error={error}
      loading={loading}
      extra={
        <Tabs
          size="small"
          activeKey={range}
          onChange={(key) => setRange(key as FocusRange)}
          items={RANGE_TABS.map((tab) => ({ key: tab.key, label: tab.label }))}
          className={styles.tabs}
        />
      }
    >
      <div className={styles.layout}>
        <div className={styles.chartBlock}>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={data.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="focusFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.primary} stopOpacity={0.26} />
                  <stop offset="100%" stopColor={colors.primary} stopOpacity={0.02} />
                </linearGradient>
              </defs>

              <CartesianGrid stroke={colors.divider} strokeDasharray="4 4" vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={{ fill: colors.textSecondary, fontSize: 11, fontWeight: 300 }}
                dy={8}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[1, 5]}
                ticks={[1, 2, 3, 4, 5]}
                tickLine={false}
                axisLine={false}
                tick={{ fill: colors.textSecondary, fontSize: 11, fontWeight: 300 }}
                width={48}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: colors.primarySoft }} />
              <Area
                type="monotone"
                dataKey="score"
                stroke={colors.primary}
                strokeWidth={2}
                fill="url(#focusFill)"
                connectNulls={false}
                dot={{ r: 3, fill: '#ffffff', stroke: colors.primary, strokeWidth: 2 }}
                activeDot={{ r: 5, fill: colors.primary, stroke: '#ffffff', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className={styles.gaugeBlock}>
          <FocusGauge average={data.average} />
          <div className={styles.gaugeCaption}>
            {RANGE_TEXT[range]}平均专注度
            {data.sampleCount > 0 ? (
              <span className={styles.sampleCount}>· 共 {data.sampleCount} 次记录</span>
            ) : null}
          </div>
        </div>
      </div>

      <p className={styles.comment}>{data.comment}</p>
    </SectionCard>
  );
}

export default FocusCard;

/**
 * 模块③ 学科分配：环形图展示各学科时长占比，右侧竖排图例。
 */

import { useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import SectionCard from './SectionCard';
import styles from './SubjectCard.module.css';
import {
  fetchSubjectDistribution,
  placeholderSubjectDistribution,
} from '@/services/subjectDistribution';
import { usePanelData } from '@/hooks/usePanelData';
import { formatDuration } from '@/utils/aggregate';
import type { SubjectSlice } from '@/types/view';

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: SubjectSlice }>;
}) {
  const slice = payload?.[0]?.payload;
  if (!active || !slice) return null;

  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipTitle}>
        <span className={styles.tooltipDot} style={{ background: slice.color }} />
        {slice.label}
      </div>
      <div className={styles.tooltipValue}>
        {formatDuration(slice.minutes)} · {(slice.ratio * 100).toFixed(1)}%
      </div>
    </div>
  );
}

function SubjectCard() {
  const { data, loading, source, error } = usePanelData(
    fetchSubjectDistribution,
    placeholderSubjectDistribution(),
  );
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const isEmpty = data.slices.length === 0;

  return (
    <SectionCard
      index="③"
      title="学科分配"
      subtitle="近三十日时长占比"
      source={source}
      error={error}
      loading={loading}
    >
      {isEmpty ? (
        <p className={styles.empty}>还没有足够的记录来描摹分布，先去学一会儿吧。</p>
      ) : (
        <div className={styles.layout}>
          <div className={styles.chart}>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={data.slices}
                  dataKey="minutes"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius={62}
                  outerRadius={92}
                  paddingAngle={2}
                  stroke="#ffffff"
                  strokeWidth={2}
                  onMouseEnter={(_, index) => setActiveIndex(index)}
                  onMouseLeave={() => setActiveIndex(null)}
                >
                  {data.slices.map((slice, index) => (
                    <Cell
                      key={slice.subject}
                      fill={slice.color}
                      opacity={activeIndex === null || activeIndex === index ? 1 : 0.45}
                    />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>

            <div className={styles.centerLabel}>
              <div className={styles.centerValue}>{formatDuration(data.totalMinutes)}</div>
              <div className={styles.centerCaption}>累计投入</div>
            </div>
          </div>

          <ul className={styles.legend}>
            {data.slices.map((slice, index) => (
              <li
                key={slice.subject}
                className={[
                  styles.legendItem,
                  activeIndex === index ? styles.legendItemActive : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseLeave={() => setActiveIndex(null)}
              >
                <span className={styles.legendDot} style={{ background: slice.color }} />
                <span className={styles.legendName}>{slice.label}</span>
                <span className={styles.legendPercent}>{(slice.ratio * 100).toFixed(0)}%</span>
                <span className={styles.legendMinutes}>{formatDuration(slice.minutes)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className={styles.poem}>各有偏重，也各有回响。</p>
    </SectionCard>
  );
}

export default SubjectCard;

/**
 * 模块卡片外壳：统一标题排版、留白、圆角与轻阴影，并如实标注数据来源。
 */

import type { ReactNode } from 'react';
import { Tooltip } from 'antd';
import styles from './SectionCard.module.css';
import type { DataSource } from '@/types/view';

interface SectionCardProps {
  /** 模块序号，如 ① */
  index: string;
  title: string;
  subtitle?: string;
  /** 标题栏右侧的操作区，如 Tab 切换 */
  extra?: ReactNode;
  source: DataSource;
  error?: string | null;
  loading?: boolean;
  children: ReactNode;
}

function SectionCard({
  index,
  title,
  subtitle,
  extra,
  source,
  error,
  loading = false,
  children,
}: SectionCardProps) {
  return (
    <section className={styles.card}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.index}>{index}</span>
          <h2 className={styles.title}>{title}</h2>
          {subtitle ? <span className={styles.subtitle}>{subtitle}</span> : null}
        </div>

        <div className={styles.headerRight}>
          {source === 'placeholder' ? (
            <Tooltip title={error ?? '后端接口尚未接通，当前展示的是占位数据'}>
              <span className={styles.placeholderBadge}>占位数据</span>
            </Tooltip>
          ) : source === 'cache' ? (
            <Tooltip
              title={error ? `${error}，当前展示的是上次缓存的数据` : '当前展示的是上次缓存的数据'}
            >
              <span className={styles.cacheBadge}>缓存数据</span>
            </Tooltip>
          ) : null}
          {loading ? <span className={styles.loadingHint}>更新中…</span> : null}
          {extra}
        </div>
      </header>

      <div className={styles.body}>{children}</div>
    </section>
  );
}

export default SectionCard;

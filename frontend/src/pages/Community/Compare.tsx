/**
 * 模块三 · 页面 2：横向对比页（/community/compare）
 * ------------------------------------------------------------
 * 读取 localStorage 中的 community_my_data 与 community_pool，渲染：
 *  1. 个人数据卡片（进度条 + 数字）
 *  2. 百分位对比（横向条形图 + 用户位置圆点）
 *  3. 分布直方图（用户值用竖线标出）
 *  4. 同学科对比（同学科子集内重算百分位，更精准）
 * 未提交过数据时显示空状态并引导去上传页。
 */

import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import styles from './index.module.css'
import { subjectLabels } from '../../styles/theme'
import {
  METRICS,
  ensurePool,
  histogram,
  loadMyData,
  percentile,
  type CommunityRecord,
  type MetricMeta,
} from './community'

/** 指标在自身量程内的归一化位置（0-100），用于进度条与竖线定位 */
function ratioOf(meta: MetricMeta, value: number): number {
  const clamped = Math.min(Math.max(value, meta.min), meta.max)
  return ((clamped - meta.min) / (meta.max - meta.min)) * 100
}

function formatValue(meta: MetricMeta, value: number): string {
  return meta.unit === '%' ? `${value}%` : `${value}`
}

/** 2. 百分位条形图：轨道 = 0-100%，填充 = 超过的人群比例，圆点 = 你的位置 */
function PercentileBar({ percent }: { percent: number }) {
  return (
    <div className={styles.pTrack} role="img" aria-label={`超过群体中 ${percent}% 的人`}>
      <div className={styles.pFill} style={{ width: `${percent}%` }} />
      <span className={styles.pDot} style={{ left: `${percent}%` }} />
    </div>
  )
}

/** 3. 分布直方图：横轴数值区间，纵轴人数；用户值用竖线标出 */
function Histogram({ meta, pool, myValue }: { meta: MetricMeta; pool: CommunityRecord[]; myValue: number }) {
  const counts = useMemo(
    () => histogram(pool, meta.key, meta.min, meta.max, meta.bins),
    [pool, meta],
  )
  const maxCount = Math.max(...counts, 1)
  const mePos = ratioOf(meta, myValue)

  return (
    <div className={styles.histBlock}>
      <div className={styles.histTitle}>
        <span>{meta.shortLabel}</span>
        <span className="numeric">{formatValue(meta, myValue)}{meta.unit === '%' ? '' : ` ${meta.unit}`}</span>
      </div>
      <div className={styles.hist}>
        {counts.map((c, i) => (
          <div
            key={i}
            className={styles.histBarWrap}
            title={`${Math.round(meta.min + ((meta.max - meta.min) / meta.bins) * i)} - ${Math.round(meta.min + ((meta.max - meta.min) / meta.bins) * (i + 1))}：${c} 人`}
          >
            <div className={styles.histBar} style={{ height: `${(c / maxCount) * 100}%` }} />
          </div>
        ))}
        <span className={styles.histMe} style={{ left: `${mePos}%` }}>
          <i>你</i>
        </span>
      </div>
      <div className={styles.histAxis}>
        <span>{meta.min}</span>
        <span>{meta.max}{meta.unit === '%' ? '%' : ''}</span>
      </div>
    </div>
  )
}

export default function CommunityComparePage() {
  // 懒初始化：渲染前确保池子存在，再一次性读入（纯本地数据，无需 effect）
  const [pool, my] = useMemo(() => {
    const p = ensurePool()
    return [p, loadMyData()] as const
  }, [])

  if (!my) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <header className={styles.pageHeader}>
            <h1 className={styles.pageTitle}>群体对比</h1>
          </header>
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>还没有你的数据。先匿名提交本周学习状态，再来看看自己在群体中的位置。</p>
            <Link to="/community/upload" className={styles.linkBtn}>
              去匿名提交 →
            </Link>
          </section>
        </div>
      </div>
    )
  }

  const subjectPool = pool.filter((r) => r.subject === my.subject)
  const subjectName = subjectLabels[my.subject] ?? my.subject

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>群体对比</h1>
          <p className={styles.pageSubtitle}>
            与 {pool.length} 份匿名数据的横向对比 · 你的学科：{subjectName}
          </p>
        </header>

        {/* 1. 个人数据卡片 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>我的数据</h2>
          <div className={styles.myGrid}>
            {METRICS.map((meta) => (
              <div key={meta.key} className={styles.myItem}>
                <div className={styles.myItemHead}>
                  <span>{meta.shortLabel}</span>
                  <span className={`${styles.myValue} numeric`}>
                    {formatValue(meta, my[meta.key])}
                    {meta.unit !== '%' && <small> {meta.unit}</small>}
                  </span>
                </div>
                <div className={styles.myTrack}>
                  <div className={styles.myFill} style={{ width: `${ratioOf(meta, my[meta.key])}%` }} />
                </div>
              </div>
            ))}
            <div className={styles.myItem}>
              <div className={styles.myItemHead}>
                <span>学科</span>
                <span className={styles.subjectChip}>{subjectName}</span>
              </div>
              <p className={styles.mySubjectNote}>同学科对比见下方</p>
            </div>
          </div>
        </section>

        {/* 2. 百分位对比 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>百分位对比</h2>
          <div className={styles.pList}>
            {METRICS.map((meta) => {
              const pct = percentile(pool, meta.key, my[meta.key])
              return (
                <div key={meta.key} className={styles.pItem}>
                  <p className={styles.pText}>
                    你的{meta.shortLabel}超过了群体中 <strong className="numeric">{pct}%</strong> 的人
                  </p>
                  <PercentileBar percent={pct} />
                  <div className={styles.pScale}>
                    <span>0%</span>
                    <span>50%</span>
                    <span>100%</span>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* 3. 分布直方图 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>群体分布</h2>
          <div className={styles.histGrid}>
            {METRICS.map((meta) => (
              <Histogram key={meta.key} meta={meta} pool={pool} myValue={my[meta.key]} />
            ))}
          </div>
        </section>

        {/* 4. 同学科对比 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>同学科对比</h2>
          {subjectPool.length > 1 ? (
            <div className={styles.subjectList}>
              {METRICS.map((meta) => {
                const pct = percentile(subjectPool, meta.key, my[meta.key])
                return (
                  <p key={meta.key} className={styles.subjectLine}>
                    在同选 <strong>{subjectName}</strong> 的{' '}
                    <strong className="numeric">{subjectPool.length}</strong> 人中， 你的{meta.shortLabel}超过{' '}
                    <strong className="numeric">{pct}%</strong> 的人
                  </p>
                )
              })}
              <p className={styles.subjectNote}>同学科样本更接近你的学习场景，比全量对比更有参考价值。</p>
            </div>
          ) : (
            <p className={styles.subjectNote}>
              目前同选{subjectName}的匿名数据太少（{subjectPool.length} 条），暂不做同学科对比，可参考上方全量结果。
            </p>
          )}
        </section>

        <div className={styles.actions}>
          <Link to="/community/upload" className={styles.linkBtnGhost}>
            重新提交本周数据 →
          </Link>
        </div>

        <p className={styles.pageFooter}>comparison is for reference, not for anxiety.</p>
      </div>
    </div>
  )
}

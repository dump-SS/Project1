/**
 * 模块三 · 页面 2：横向对比页（/community/compare）
 * ------------------------------------------------------------
 * M4 转正（决策 v1.7 §5.4）：只消费服务端聚合，不在前端计算他人个体特征。
 * - 未授权 → 授权引导空态（COMMUNITY_CONSENT_REQUIRED）
 * - 样本不足 → 「群体数据积累中」空态（COMMUNITY_INSUFFICIENT_POOL，不展示缺口人数）
 * - 服务不可用/聚合未生成 → 降级提示，不白屏
 * 展示内容：分位数（p25/p50/p75）+ 直方图（已做 count<3 桶合并）+「我的位置」标记（本端数值）。
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import styles from './index.module.css'
import { ApiError } from '../../services/http'
import {
  fetchCommunityAggregate,
  fetchCommunityConsent,
  type CommunityAggregate,
  type CommunityMetric,
  type CommunityStage,
} from '../../services/communityApi'
import { loadMyData, METRICS } from './community'

const STAGE_OPTIONS: { value: CommunityStage; label: string }[] = [
  { value: 'junior', label: '初中' },
  { value: 'senior', label: '高中' },
]

const METRIC_OPTIONS: { value: CommunityMetric; label: string }[] = [
  { value: 'hours', label: '学习时长' },
  { value: 'focus', label: '专注度' },
  { value: 'fatigue', label: '疲劳度' },
  { value: 'completion', label: '完成率' },
]

function formatValue(metric: CommunityMetric, value: number): string {
  if (metric === 'completion') return `${Math.round(value * 100)}%`
  if (metric === 'hours') return `${value} 小时`
  return `${value}`
}

export default function CommunityComparePage() {
  const my = useMemo(() => loadMyData(), [])

  const [consent, setConsent] = useState<boolean | null>(null)
  const [stage, setStage] = useState<CommunityStage>('senior')
  const [metric, setMetric] = useState<CommunityMetric>('hours')
  const [data, setData] = useState<CommunityAggregate | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<{ code?: string; message?: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchCommunityConsent()
      .then((d) => { if (!cancelled) setConsent(d.enabled) })
      .catch(() => { if (!cancelled) setConsent(null) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (consent !== true) { setData(null); return }
    let cancelled = false
    setLoading(true)
    setErr(null)
    fetchCommunityAggregate(stage, metric)
      .then((d) => { if (!cancelled) { setData(d); setErr(null) } })
      .catch((e) => {
        if (cancelled) return
        const code = e instanceof ApiError ? e.code : undefined
        setData(null)
        if (code === 'COMMUNITY_INSUFFICIENT_POOL') {
          setErr({ code, message: '群体数据积累中，暂不展示对比' })
        } else if (code === 'COMMUNITY_CONSENT_REQUIRED') {
          setErr({ code, message: '开启匿名聚合授权后才能查看' })
        } else {
          setErr({ message: e instanceof Error ? e.message : '服务不可用，请稍后再试' })
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [consent, stage, metric])

  // 未授权
  if (consent === false) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <header className={styles.pageHeader}><h1 className={styles.pageTitle}>群体对比</h1></header>
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>尚未开启匿名聚合授权。开启后（需监护人授权）你的本周特征将参与同龄群体匿名对比，可随时撤回。</p>
            <Link to="/settings" className={styles.linkBtn}>去设置开启授权 →</Link>
          </section>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>群体对比</h1>
          <p className={styles.pageSubtitle}>与同龄群体的聚合参照 · 只发聚合，不发个体</p>
        </header>

        {/* 我的本周数据（本端草稿，不与池混合） */}
        {my && (
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>我的本周数据</h2>
            <div className={styles.myGrid}>
              {METRICS.map((m) => (
                <div key={m.key} className={styles.myItem}>
                  <div className={styles.myItemHead}>
                    <span>{m.shortLabel}</span>
                    <span className={`${styles.myValue} numeric`}>
                      {m.key === 'completion' ? `${my[m.key]}%` : my[m.key]}
                      {m.unit !== '%' && <small> {m.unit}</small>}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 查询参数 */}
        <section className={styles.card}>
          <div className={styles.fieldRow}>
            <div className={styles.fieldLabel}><span>学段</span></div>
            <div className={styles.fieldControl}>
              <select className={styles.select} value={stage} onChange={(e) => setStage(e.target.value as CommunityStage)}>
                {STAGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className={styles.fieldLabel}><span>指标</span></div>
            <div className={styles.fieldControl}>
              <select className={styles.select} value={metric} onChange={(e) => setMetric(e.target.value as CommunityMetric)}>
                {METRIC_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
        </section>

        {/* 结果 / 三异常态 */}
        {loading && <p className={styles.pageSubtitle}>加载中…</p>}
        {err && (
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>{err.message ?? '服务不可用，请稍后再试'}</p>
            {err.code === 'COMMUNITY_CONSENT_REQUIRED' && (
              <Link to="/settings" className={styles.linkBtn}>去设置开启授权 →</Link>
            )}
          </section>
        )}

        {!loading && !err && data && (
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>群体分布 · {data.poolSize} 人</h2>
            <div className={styles.pList}>
              <p className={styles.pText}>中位数（p50）：<strong className="numeric">{formatValue(data.metric, data.percentiles.p50)}</strong></p>
              <p className={styles.pText}>p25 / p75：{formatValue(data.metric, data.percentiles.p25)} ~ {formatValue(data.metric, data.percentiles.p75)}</p>
            </div>
            <div className={styles.histGrid}>
              {data.histogram.map((b, i) => (
                <div key={i} className={styles.histBarWrap} title={`${b.lo}${b.hi === null ? '+' : ` - ${b.hi}`}：${b.count} 人`}>
                  <div className={styles.histBar} style={{ height: `${Math.max(8, (b.count / (data.poolSize || 1)) * 200)}px` }} />
                  <span className={styles.histAxisLabel}>{b.lo}{b.hi === null ? '+' : ''}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className={styles.actions}>
          <Link to="/community/upload" className={styles.linkBtnGhost}>返回录入 →</Link>
        </div>
        <p className={styles.pageFooter}>群体数据积累中 · 演示期间仅展示真实聚合，不混排演示数据。</p>
      </div>
    </div>
  )
}

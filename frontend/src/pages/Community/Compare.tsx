/**
 * 模块三 · 页面 2：横向对比页（/community/compare）
 * ------------------------------------------------------------
 * M4 转正（决策 v1.7 §5.4）：只消费服务端聚合，不在前端计算他人个体特征。
 * 数据源全部为真接口（services/communityApi.ts）：
 * - GET  /me/community-consent  授权状态（决定页面显示什么）
 * - PUT  /me/community-consent  显式开启（可能是本页唯一的数据写动作）
 * - GET  /community/aggregate   只读服务端聚合（stage + metric 必填）
 *
 * 四个异常态**分别处理**，不合并成统一空态（隐私底线：不显示数值的场景不是一个）：
 * | 错误码 | HTTP | 页面必须做的 |
 * |---|---|---|
 * | COMMUNITY_CONSENT_REQUIRED      | 403 | 给出去授权入口，**不渲染任何数值** |
 * | GUARDIAN_AUTHORIZATION_REQUIRED | 403 | 引导至「设置 → 授权与隐私」（未满 14 岁需监护人授权） |
 * | GUARDIAN_AUTHORIZATION_EXPIRED  | 403 | 同上，并提示需重新确认 |
 * | COMMUNITY_INSUFFICIENT_POOL     | 503 | 只显示"人数还不够"，**不显示任何数字** |
 *
 * ⚠️ 本页**不使用** localStorage 假数据（community_pool / community_my_data 已随 community.ts 下线）：
 * 服务端每周抽取是唯一真源，客户端不上传、不参与、不本地计算。
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import styles from './index.module.css'
import { ApiError } from '../../services/http'
import {
  fetchCommunityAggregate,
  fetchCommunityConsent,
  putCommunityConsent,
  type CommunityAggregate,
  type CommunityMetric,
  type CommunityStage,
} from '../../services/communityApi'
import { getMe } from '../../services/user'

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

/** 各指标的取值区间（只用于分位数刻度条的相对定位，与契约的桶边界无关） */
const METRIC_RANGE: Record<CommunityMetric, { min: number; max: number }> = {
  hours: { min: 0, max: 40 },
  focus: { min: 1, max: 5 },
  fatigue: { min: 1, max: 5 },
  completion: { min: 0, max: 1 },
}

function formatValue(metric: CommunityMetric, value: number): string {
  // 契约 CommunityAggregate.percentiles：completion 为 0–1 小数，其余为原值
  if (metric === 'completion') return `${Math.round(value * 100)}%`
  if (metric === 'hours') return `${value} 小时`
  return `${value}`
}

/** 分位数在刻度条上的百分比位置（越界收敛到 0–100） */
function scalePercent(metric: CommunityMetric, value: number): number {
  const { min, max } = METRIC_RANGE[metric]
  if (max === min) return 0
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))
}

/**
 * 四个错误码各自的呈现口径 —— 分开定义，避免退回"一个 if 吃四种情况"。
 * `guardianPrompt` 只在监护人授权那两类里出现，因为这两类的动作是"去完成/重做授权"，
 * 与"去开启开关"不是同一件事。
 */
type ErrorKind = 'consent' | 'guardianRequired' | 'guardianExpired' | 'pool' | 'rate' | 'other'

interface ErrorView {
  kind: ErrorKind
  text: string
  /** 是否给出「去设置 → 授权与隐私」入口 */
  toPrivacy: boolean
}

function describeError(err: unknown): ErrorView {
  const code = err instanceof ApiError ? err.code : undefined
  switch (code) {
    case 'COMMUNITY_CONSENT_REQUIRED':
      return { kind: 'consent', text: '尚未开启匿名聚合授权。开启后才能查看同龄群体参照。', toPrivacy: false }
    case 'GUARDIAN_AUTHORIZATION_REQUIRED':
      return {
        kind: 'guardianRequired',
        text: '开启群体参照需要先完成监护人授权。请前往「设置 → 授权与隐私」完成监护人确认后再回来开启。',
        toPrivacy: true,
      }
    case 'GUARDIAN_AUTHORIZATION_EXPIRED':
      return {
        kind: 'guardianExpired',
        text: '监护人授权已失效（已过期或已撤回），需要重新确认授权后才能开启群体参照。',
        toPrivacy: true,
      }
    case 'COMMUNITY_INSUFFICIENT_POOL':
      // 隐私底线：样本不足时服务端不下发任何数值，本页也不得出现任何数字
      return { kind: 'pool', text: '参加对比的人数还不够，暂时无法展示群体分布。', toPrivacy: false }
    case 'RATE_LIMITED':
      return { kind: 'rate', text: '查询太频繁了，请稍等一分钟再试。', toPrivacy: false }
    default:
      return {
        kind: 'other',
        text: err instanceof Error && err.message ? err.message : '服务不可用，请稍后再试。',
        toPrivacy: false,
      }
  }
}

export default function CommunityComparePage() {
  /** null = 授权状态加载中（此时不渲染任何结果区，避免未授权态闪现数值） */
  const [consent, setConsent] = useState<boolean | null>(null)
  const [stage, setStage] = useState<CommunityStage>('senior')
  const [metric, setMetric] = useState<CommunityMetric>('hours')
  const [data, setData] = useState<CommunityAggregate | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<ErrorView | null>(null)
  /** 开启授权请求进行中 / 其失败原因（与查询错误分开，否则会与四个错误码语义混淆） */
  const [enabling, setEnabling] = useState(false)
  const [enableErr, setEnableErr] = useState<ErrorView | null>(null)

  // 授权状态：决定页面走到哪一步
  const loadConsent = useCallback(() => {
    let cancelled = false
    fetchCommunityConsent()
      .then((d) => { if (!cancelled) setConsent(d.enabled) })
      // 读取失败（含未登录 401）不能当成"已授权"，否则会去请求聚合、拿到 403 后文案错位
      .catch(() => { if (!cancelled) setConsent(null) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const cancel = loadConsent()
    return cancel
  }, [loadConsent])

  // 学段默认值取建档信息（openapi User.stage 与聚合的 stage 枚举同源：junior / senior）
  const [stageTouched, setStageTouched] = useState(false)
  useEffect(() => {
    let cancelled = false
    getMe()
      .then((u) => {
        if (cancelled || stageTouched) return
        if (u?.stage === 'junior' || u?.stage === 'senior') setStage(u.stage)
      })
      // 拿不到建档信息不算错误：保留默认学段，用户可自行切换
      .catch(() => {})
    return () => { cancelled = true }
  }, [stageTouched])

  // 聚合数据：只在明确已授权时请求
  useEffect(() => {
    if (consent !== true) { setData(null); return }
    let cancelled = false
    setLoading(true)
    setErr(null)
    fetchCommunityAggregate(stage, metric)
      .then((d) => { if (!cancelled) { setData(d); setErr(null) } })
      .catch((e) => {
        if (cancelled) return
        setData(null)
        setErr(describeError(e))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [consent, stage, metric])

  /** 显式开启授权：唯一的数据写动作。监护人授权未满足时后端返回两个不同的 403。 */
  const handleEnable = async () => {
    setEnabling(true)
    setEnableErr(null)
    try {
      const next = await putCommunityConsent(true)
      setConsent(next.enabled)
      if (next.enabled) setErr(null)
    } catch (e) {
      setEnableErr(describeError(e))
    } finally {
      setEnabling(false)
    }
  }

  /** 「重试」只重发当前这一步（查询失败重发查询；开启失败重发开启），不做盲目轮询 */
  const retry = () => {
    if (enableErr) { handleEnable(); return }
    setErr(null)
    setData(null)
    setConsent(null) // 回到「读取授权状态」这一步，拿到结果后由查询 effect 重新取数
    loadConsent()
  }

  const header = (
    <header className={styles.pageHeader}>
      <h1 className={styles.pageTitle}>群体对比</h1>
      <p className={styles.pageSubtitle}>与同龄群体的聚合参照 · 只发聚合，不发个体</p>
    </header>
  )

  // ① 授权状态未拿到（加载中或读取失败）：既不给数值也不给开启按钮
  if (consent === null) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          {header}
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>正在读取匿名聚合授权状态…</p>
            <button type="button" className={styles.linkBtn} onClick={loadConsent}>
              重新读取
            </button>
          </section>
        </div>
      </div>
    )
  }

  // ② 未授权：给出授权入口，页面不渲染任何数值
  if (consent === false) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          {header}
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>
              尚未开启匿名聚合授权。开启后，你每周的学习特征将由服务端匿名抽取并参与同龄群体对比，
              随时可以在设置里撤回（撤回即删除已抽取的特征）。
            </p>

            <button
              type="button"
              className={styles.submitBtn}
              disabled={enabling}
              onClick={handleEnable}
            >
              {enabling ? '正在开启…' : '开启匿名聚合授权'}
            </button>

            {/* 开启动作的失败原因：两个监护人授权 403 与其它错误分开呈现 */}
            {enableErr && (
              <p className={styles.privacyNote}>{enableErr.text}</p>
            )}
            {enableErr?.toPrivacy && (
              <Link to="/settings?tab=privacy" className={styles.linkBtn}>
                前往授权与隐私 →
              </Link>
            )}

            <p className={styles.privacyNote}>
              未满 14 岁需先完成监护人授权；开启前不会上传你的任何数据。
            </p>
          </section>
        </div>
      </div>
    )
  }

  // ③ 已授权：查询与结果
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {header}

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>授权状态</h2>
          <div className={styles.myGrid}>
            <div className={styles.myItemHead}>
              <span>匿名聚合授权</span>
              <span className={styles.myValue}>已开启</span>
            </div>
          </div>
          <p className={styles.privacyNote}>
            你的特征由服务端每周自动匿名抽取，本页只读取聚合结果；撤回可在「设置 → 授权与隐私」完成。
          </p>
          <div className={styles.actions}>
            <Link to="/settings?tab=privacy" className={styles.linkBtnGhost}>
              撤回 / 管理授权 →
            </Link>
          </div>
        </section>

        {/* 查询参数：stage + metric 均为必填 */}
        <section className={styles.card}>
          <div className={styles.fieldRow}>
            <div className={styles.fieldLabel}><span>学段</span></div>
            <div className={styles.fieldControl}>
              <select
                className={styles.select}
                value={stage}
                onChange={(e) => { setStageTouched(true); setStage(e.target.value as CommunityStage) }}
              >
                {STAGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className={styles.fieldLabel}><span>指标</span></div>
            <div className={styles.fieldControl}>
              <select
                className={styles.select}
                value={metric}
                onChange={(e) => setMetric(e.target.value as CommunityMetric)}
              >
                {METRIC_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
        </section>

        {loading && <p className={styles.pageSubtitle}>加载中…</p>}

        {/* 四个错误码的落点（分别渲染，不合并） */}
        {!loading && err && (
          <section className={`${styles.card} ${styles.emptyCard}`}>
            <p className={styles.emptyText}>{err.text}</p>
            {err.toPrivacy && (
              <Link to="/settings?tab=privacy" className={styles.linkBtn}>
                前往授权与隐私 →
              </Link>
            )}
            {err.kind === 'consent' && (
              <button type="button" className={styles.linkBtn} onClick={handleEnable} disabled={enabling}>
                {enabling ? '正在开启…' : '开启匿名聚合授权'}
              </button>
            )}
            {err.kind === 'pool' && (
              <p className={styles.privacyNote}>
                为保证匿名性，样本不足时不会展示任何数值，也不显示还差多少人。
              </p>
            )}
            {(err.kind === 'rate' || err.kind === 'other') && (
              <button type="button" className={styles.linkBtn} onClick={retry}>
                重试
              </button>
            )}
          </section>
        )}

        {!loading && !err && data && (
          <section className={styles.card}>
            {/* poolSize 由服务端在 k≥20 时下发；此处不做前端阈值判断 */}
            <h2 className={styles.cardTitle}>群体分布 · 同龄群体 {data.poolSize} 人</h2>
            <p className={styles.pageSubtitle}>周期 {data.period} · {METRIC_OPTIONS.find((o) => o.value === data.metric)?.label}</p>

            <div className={styles.pList}>
              <div className={styles.pText}>
                中位数（p50）
                <strong className="numeric">{formatValue(data.metric, data.percentiles.p50)}</strong>
              </div>
              <div className={styles.pTrack}>
                <span
                  className={styles.pFill}
                  style={{
                    left: `${scalePercent(data.metric, data.percentiles.p25)}%`,
                    width: `${Math.max(
                      0,
                      scalePercent(data.metric, data.percentiles.p75) -
                        scalePercent(data.metric, data.percentiles.p25),
                    )}%`,
                  }}
                />
                <span
                  className={styles.pDot}
                  style={{ left: `${scalePercent(data.metric, data.percentiles.p50)}%` }}
                />
              </div>
              <p className={styles.pText}>
                p25 / p75：{formatValue(data.metric, data.percentiles.p25)} ~ {formatValue(data.metric, data.percentiles.p75)}
              </p>
            </div>

            <div className={styles.histGrid}>
              {data.histogram.map((b) => (
                <div
                  key={`${b.lo}-${b.hi ?? 'open'}`}
                  className={styles.histBarWrap}
                  title={`${b.lo}${b.hi === null ? ' 以上' : ` - ${b.hi}`}：${b.count} 人`}
                >
                  <div
                    className={styles.histBar}
                    style={{ height: `${Math.max(8, (b.count / (data.poolSize || 1)) * 200)}px` }}
                  />
                  {/* hi 为 null = 顶桶开放区间，用「32h+」这类开放标签 */}
                  <span className={styles.histAxisLabel}>{b.lo}{b.hi === null ? '+' : ''}</span>
                </div>
              ))}
            </div>

            <div className={styles.hist}>
              <div className={styles.histTitle}>
                共 {data.poolSize} 名同龄参与者的分布（桶内不足 3 人已由服务端合并）
              </div>
            </div>
          </section>
        )}

        <div className={styles.actions}>
          {/* /community 本身是重定向到 /community/upload 的别名，直接指真身避免多一跳 */}
          <Link to="/community/upload" className={styles.linkBtnGhost}>返回说明页 →</Link>
        </div>
        <p className={styles.pageFooter}>
          全部数值来自服务端聚合，本页不混排演示数据，也不在本地计算他人特征。
        </p>
      </div>
    </div>
  )
}

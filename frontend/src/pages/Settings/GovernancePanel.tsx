/**
 * 设置 · 运营治理面板 —— G 板块（用量 / 奖章 / 报错常驻入口）。
 *
 * 挂载在 Settings 页（G 卡前端目录：「设置内用量页、报错入口、奖章展示」）。
 * 结构优先：只做信息结构，不引入视觉风格（UI 未拍板，#51）。
 *
 * - 用量：GET /me/usage 月度只读视图。pilot 不收费，只为定价留数据（D38/#9），
 *   **无任何支付/充值入口**（支付整体推迟到 pilot 后）。
 * - 奖章：GET /me/medals（#49 最小版 5 里程碑；不做积分商城/排行榜）。
 * - 报错：POST /error-reports 常驻入口（#46 第①处；第②处消息级按钮见
 *   components/ErrorReportButton，B 板块在 Chat 挂载）。
 */
import { useEffect, useMemo, useState } from 'react'
import { getMyMedals, getMyUsage } from '@/services/usage'
import { postErrorReport } from '@/services/feedback'
import { isNetworkError } from '@/services/http'
import type { MedalMilestone, UsageFeatureTier } from '@/types/governance'
import styles from './GovernancePanel.module.css'

const TIER_LABELS: Record<UsageFeatureTier, string> = {
  chat: '对话',
  embedded: '系统自动',
  advanced: '高级',
  multimodal: '文件解析',
}

const MILESTONES: Array<{ key: MedalMilestone; title: string; desc: string }> = [
  { key: 'first_record', title: '第一步', desc: '第一次记录学习' },
  { key: 'streak_7_days', title: '七日之约', desc: '连续 7 天记录学习' },
  { key: 'first_summary', title: '回望', desc: '第一次完成复盘' },
  { key: 'first_goal_achieved', title: '说到做到', desc: '第一个目标达成' },
  { key: 'first_topic_book', title: '错题归档', desc: '题本收入第一条' },
]

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function GovernancePanel() {
  return (
    <>
      <UsageSection />
      <MedalSection />
      <ErrorReportSection />
    </>
  )
}

// ===== 用量（只读） =====

function UsageSection() {
  const [month, setMonth] = useState(currentMonth)
  const [data, setData] = useState<Awaited<ReturnType<typeof getMyUsage>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getMyUsage(month)
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(isNetworkError(e) ? '用量服务暂不可用' : (e?.message ?? '读取失败')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [month])

  const byTier = useMemo(() => {
    const map = new Map<UsageFeatureTier, { calls: number; tokensIn: number; tokensOut: number; cost: number }>()
    for (const it of data?.items ?? []) {
      const cur = map.get(it.featureTier) ?? { calls: 0, tokensIn: 0, tokensOut: 0, cost: 0 }
      cur.calls += 1
      cur.tokensIn += it.tokensIn
      cur.tokensOut += it.tokensOut
      cur.cost += it.cost
      map.set(it.featureTier, cur)
    }
    return [...map.entries()]
  }, [data])

  return (
    <section className={styles.card}>
      <div className={styles.cardHeader}>
        <h2 className={styles.cardTitle}>AI 用量</h2>
        <div className={styles.monthNav}>
          <button type="button" className={styles.monthBtn} onClick={() => setMonth((m) => shiftMonth(m, -1))} aria-label="上一月">‹</button>
          <span className={styles.monthLabel}>{month}</span>
          <button
            type="button"
            className={styles.monthBtn}
            onClick={() => setMonth((m) => shiftMonth(m, 1))}
            disabled={month >= currentMonth()}
            aria-label="下一月"
          >
            ›
          </button>
        </div>
      </div>
      <p className={styles.cardDesc}>
        测试阶段不收费，这里只记录 AI 调用的用量与数值成本，供我们了解服务成本、规划后续方案。只读，不影响你的任何权益。
      </p>

      {loading ? <p className={styles.hint}>加载中…</p> : null}
      {error ? <p className={styles.error}>{error}</p> : null}

      {data && !loading ? (
        data.items.length === 0 ? (
          <p className={styles.hint}>本月暂无 AI 调用记录</p>
        ) : (
          <>
            <div className={styles.usageTotals}>
              <div className={styles.totalCell}>
                <span className={styles.totalLabel}>调用次数</span>
                <span className={styles.totalValue}>{data.items.length}</span>
              </div>
              <div className={styles.totalCell}>
                <span className={styles.totalLabel}>输入 tokens</span>
                <span className={styles.totalValue}>{fmt(data.totalTokensIn)}</span>
              </div>
              <div className={styles.totalCell}>
                <span className={styles.totalLabel}>输出 tokens</span>
                <span className={styles.totalValue}>{fmt(data.totalTokensOut)}</span>
              </div>
              <div className={styles.totalCell}>
                <span className={styles.totalLabel}>数值成本</span>
                <span className={styles.totalValue}>{(data.totalCost ?? 0).toFixed(2)}</span>
              </div>
            </div>

            {byTier.length > 0 ? (
              <ul className={styles.tierList}>
                {byTier.map(([tier, s]) => (
                  <li key={tier} className={styles.tierItem}>
                    <span>{TIER_LABELS[tier] ?? tier}</span>
                    <span className={styles.tierStat}>{s.calls} 次 · {fmt(s.tokensIn + s.tokensOut)} tokens</span>
                  </li>
                ))}
              </ul>
            ) : null}

            {expanded ? (
              <table className={styles.detailTable}>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>档位</th>
                    <th>输入</th>
                    <th>输出</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((it) => (
                    <tr key={it.id}>
                      <td>{new Date(it.createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                      <td>{TIER_LABELS[it.featureTier] ?? it.featureTier}</td>
                      <td>{fmt(it.tokensIn)}</td>
                      <td>{fmt(it.tokensOut)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            <button type="button" className={styles.linkBtn} onClick={() => setExpanded((v) => !v)}>
              {expanded ? '收起明细' : '查看明细'}
            </button>
          </>
        )
      ) : null}
    </section>
  )
}

// ===== 奖章（最小版） =====

function MedalSection() {
  const [medals, setMedals] = useState<Awaited<ReturnType<typeof getMyMedals>>['items']>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    getMyMedals()
      .then((d) => { if (!cancelled) setMedals(d.items) })
      .catch((e) => { if (!cancelled) setError(isNetworkError(e) ? '奖章服务暂不可用' : (e?.message ?? '读取失败')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const earned = new Map(medals.map((m) => [m.milestone, m.awardedAt]))

  return (
    <section className={styles.card}>
      <h2 className={styles.cardTitle}>里程碑</h2>
      <p className={styles.cardDesc}>记录你学习路上的一些小节点。没有积分，没有排行。</p>
      {loading ? <p className={styles.hint}>加载中…</p> : null}
      {error ? <p className={styles.error}>{error}</p> : null}
      {!loading && !error ? (
        <ul className={styles.medalList}>
          {MILESTONES.map((m) => {
            const at = earned.get(m.key)
            return (
              <li key={m.key} className={`${styles.medalItem}${at ? styles.medalEarned : ''}`}>
                <span className={styles.medalIcon} aria-hidden>{at ? '🏅' : '·'}</span>
                <span className={styles.medalBody}>
                  <span className={styles.medalTitle}>{m.title}</span>
                  <span className={styles.medalDesc}>{at ? `${m.desc} · ${new Date(at).toLocaleDateString('zh-CN')}` : m.desc}</span>
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}

// ===== 报错（设置常驻入口，#46 第①处） =====

function ErrorReportSection() {
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    const description = text.trim()
    if (!description) return
    setSubmitting(true)
    setError('')
    try {
      await postErrorReport({ description })
      setDone(true)
      setText('')
      setTimeout(() => setDone(false), 2500)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(isNetworkError(err) ? '网络不可用，请稍后再试' : (message || '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className={styles.card}>
      <h2 className={styles.cardTitle}>遇到问题？</h2>
      <p className={styles.cardDesc}>
        功能坏了、答案不对、行为奇怪——都可以在这里告诉我们。在对话里也可以对单条回答点「报错」，那样我们能定位得更准。
      </p>
      <textarea
        className={styles.reportTextarea}
        rows={3}
        maxLength={2000}
        placeholder="简单描述你遇到的问题（必填）"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className={styles.reportActions}>
        {error ? <span className={styles.error}>{error}</span> : null}
        {done ? <span className={styles.ok}>已收到，谢谢反馈</span> : null}
        <button
          type="button"
          className={styles.reportBtn}
          disabled={submitting || !text.trim()}
          onClick={submit}
        >
          {submitting ? '提交中…' : '提交反馈'}
        </button>
      </div>
    </section>
  )
}

function fmt(n?: number): string {
  return (n ?? 0).toLocaleString('zh-CN')
}

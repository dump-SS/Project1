import { useCallback, useEffect, useRef, useState } from 'react'
import styles from './index.module.css'
import {
  createSummary,
  getSummary,
  isSummaryTerminal,
  listSummaries,
  submitSummaryFeedback,
} from '../../services/summary'
import {
  createKnowledgeSummary,
  isRateLimited,
} from '../../services/knowledgeSummary'
import type { Rating, Summary } from '@/types/api'

const RATING_OPTIONS = [
  { value: 'useful' as Rating, label: '有用' },
  { value: 'neutral' as Rating, label: '一般' },
  { value: 'not_useful' as Rating, label: '没用' },
]

const TERMINAL_REASON = {
  ready: { title: '已生成', hint: '' },
  insufficient_data: { title: '数据不足', hint: '记录太少时先不硬凑，攒够数据再生成' },
  failed: { title: '生成失败', hint: '请稍后再试，不会展示半成品' },
}

function toDateString(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function lastNDays(n: number): { start: string; end: string } {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - (n - 1))
  return { start: toDateString(start), end: toDateString(end) }
}

function daysBetween(start: string, end: string): number {
  const s = new Date(`${start}T00:00:00`)
  const e = new Date(`${end}T00:00:00`)
  return Math.round((e.getTime() - s.getTime()) / 86400000) + 1
}

/** 区间长度约束（openapi.yaml SummaryCreate：3-31 天） */
function isValidRange(start: string, end: string): boolean {
  if (!start || !end) return false
  const span = daysBetween(start, end)
  return span >= 3 && span <= 31
}

export default function SummaryReviewPage() {
  const initial = useRef(lastNDays(7))

  const [periodStart, setPeriodStart] = useState<string>(initial.current.start)
  const [periodEnd, setPeriodEnd] = useState<string>(initial.current.end)

  // v2.2：按 dimension 分 tab（状态与规划 / 知识内容）
  const [dimension, setDimension] = useState<'state_and_plan' | 'knowledge'>('state_and_plan')

  const [generating, setGenerating] = useState(false)
  const [polling, setPolling] = useState(false)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [rating, setRating] = useState<Rating | null>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState(false)

  const abortRef = useRef<AbortController | null>(null)

  const stopPolling = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setPolling(false)
    setGenerating(false)
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  // 挂载时拉取复盘列表，把与当前默认区间匹配的最新一条直接展示出来。
  // 解决「库里已有 1 条复盘数据但页面不展示」的问题。
  // v2.2：按当前 dimension 过滤（未标注 dimension 的旧数据默认 state_and_plan）。
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const result = await listSummaries(1, 20)
        if (cancelled) return
        const inDimension = (result.items ?? []).filter(
          (s) => (s.dimension ?? 'state_and_plan') === dimension,
        )
        const matched = inDimension.find(
          (s) => s.periodStart === initial.current.start && s.periodEnd === initial.current.end,
        ) ?? inDimension[0]
        if (!matched) return
        if (!isSummaryTerminal(matched.generation?.status)) return
        setSummary(matched)
        setPeriodStart(matched.periodStart ?? initial.current.start)
        setPeriodEnd(matched.periodEnd ?? initial.current.end)
        if (matched.feedback) {
          setRating(matched.feedback.rating)
          setReason(matched.feedback.reason ?? '')
          setFeedbackSent(true)
        }
      } catch {
        // 静默兜底：拉取失败就保持空状态，用户仍可手动点「生成复盘」
      }
    })()
    return () => {
      cancelled = true
    }
  }, [dimension])

  const canGenerate = isValidRange(periodStart, periodEnd) && !generating

  const handleGenerate = async () => {
    if (!canGenerate) return
    setError(null)
    setSummary(null)
    setFeedbackSent(false)
    setGenerating(true)
    setPolling(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const pending = await createSummary(periodStart, periodEnd)
      // 轮询直到生成进入终态（PRD 5.4：不展示半成品）
      const maxTries = 30
      let current = await getSummary(pending.summaryId, controller.signal)
      let tries = 1
      while (!isSummaryTerminal(current.generation.status) && tries < maxTries && !controller.signal.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (controller.signal.aborted) return
        current = await getSummary(pending.summaryId, controller.signal)
        tries += 1
      }
      setSummary(current)
    } catch (err) {
      if (controller.signal.aborted) return
      setError(err instanceof Error ? err.message : '生成失败，请稍后再试')
    } finally {
      abortRef.current = null
      setPolling(false)
      setGenerating(false)
    }
  }

  const handleSubmitFeedback = async () => {
    if (!summary || rating === null || submitting) return
    setSubmitting(true)
    try {
      await submitSummaryFeedback(summary.summaryId, rating, reason)
      setFeedbackSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '反馈提交失败，请稍后再试')
    } finally {
      setSubmitting(false)
    }
  }

  /* ----- 知识复盘（S0-T4）：知识 tab 主动触发，三异常态有明确文案 ----- */
  const [knowledgeGenerating, setKnowledgeGenerating] = useState(false)
  const [knowledgeSummary, setKnowledgeSummary] = useState<string | null>(null)
  const [knowledgeSubject, setKnowledgeSubject] = useState<'SX' | 'WL' | 'YY'>('SX')

  const handleGenerateKnowledge = async () => {
    setError(null)
    setKnowledgeSummary(null)
    setKnowledgeGenerating(true)
    try {
      const res = await createKnowledgeSummary(knowledgeSubject, '本周')
      setKnowledgeSummary(res.summary)
    } catch (err) {
      if (isRateLimited(err)) {
        setError('今日知识复盘次数已达上限，请明天再试')
      } else {
        setError(err instanceof Error ? err.message : '知识复盘生成失败，请稍后再试')
      }
    } finally {
      setKnowledgeGenerating(false)
    }
  }

  const generationStatus = summary?.generation.status
  const terminal = generationStatus && generationStatus in TERMINAL_REASON
    ? TERMINAL_REASON[generationStatus as keyof typeof TERMINAL_REASON]
    : null
  const content = summary?.content

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>学习总结 / 复盘</h1>
        <p className={styles.subtitle}>把一段时间的记录与状态变化，整理成看得懂、用得上的复盘。</p>
        <div className={styles.tabs} role="tablist">
          {([
            ['state_and_plan', '状态与规划'],
            ['knowledge', '知识内容'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={dimension === key}
              className={`${styles.tab} ${dimension === key ? styles.tabActive : ''}`}
              onClick={() => {
                setDimension(key)
                setSummary(null)
                setError(null)
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <section className={styles.panel}>
        <div className={styles.rangeRow}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>开始日期</span>
            <input
              type="date"
              className={styles.dateInput}
              value={periodStart}
              max={periodEnd}
              onChange={(e) => setPeriodStart(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>结束日期</span>
            <input
              type="date"
              className={styles.dateInput}
              value={periodEnd}
              min={periodStart}
              onChange={(e) => setPeriodEnd(e.target.value)}
            />
          </label>
          <button
            type="button"
            className={styles.generateBtn}
            disabled={!canGenerate}
            onClick={handleGenerate}
          >
            {generating ? (polling ? '生成中…' : '创建中…') : dimension === 'knowledge' ? '生成知识复盘' : '生成复盘'}
          </button>
        </div>

        {dimension === 'knowledge' && (
          <div className={styles.knowledgeRow}>
            <select
              value={knowledgeSubject}
              onChange={(e) => setKnowledgeSubject(e.target.value as 'SX' | 'WL' | 'YY')}
              className={styles.subjectSelect}
              aria-label="选择学科"
            >
              <option value="SX">数学</option>
              <option value="WL">物理</option>
              <option value="YY">英语</option>
            </select>
            <button
              type="button"
              className={styles.generateBtn}
              disabled={knowledgeGenerating}
              onClick={handleGenerateKnowledge}
            >
              {knowledgeGenerating ? '生成中…' : '生成本周知识复盘'}
            </button>
            {knowledgeSummary && (
              <div className={styles.knowledgeResult}>
                <h2 className={styles.blockTitle}>知识复盘</h2>
                <p className={styles.overview}>{knowledgeSummary}</p>
              </div>
            )}
          </div>
        )}
        {!isValidRange(periodStart, periodEnd) && (
          <p className={styles.hint}>区间长度需在 3–31 天之间。</p>
        )}
        {error && <p className={styles.error}>{error}</p>}
      </section>

      {summary && (
        <section className={styles.result}>
          <div className={styles.resultHead}>
            <span className={styles.period}>
              {summary.periodStart || ''} ~ {summary.periodEnd || ''}
            </span>
            {terminal && (
              <span className={styles.statusTag}>{terminal.title}</span>
            )}
          </div>

          {content ? (
            <div className={styles.content}>
              <div className={styles.block}>
                <h2 className={styles.blockTitle}>状态概览</h2>
                <p className={styles.overview}>{content.overview}</p>
              </div>

              <div className={styles.block}>
                <h2 className={styles.blockTitle}>观察到的规律</h2>
                <ul className={styles.list}>
                  {content.patterns.map((item, i) => (
                    <li key={i} className={styles.listItem}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className={styles.block}>
                <h2 className={styles.blockTitle}>下阶段建议</h2>
                <ul className={styles.list}>
                  {content.suggestions.map((item, i) => (
                    <li key={i} className={styles.listItem}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className={styles.block}>
                <p className={styles.encouragement}>{content.encouragement}</p>
              </div>
            </div>
          ) : (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>{terminal?.title ?? '暂无内容'}</p>
              <p className={styles.emptyText}>{summary.message ?? terminal?.hint ?? ''}</p>
              {summary.dataPoints && summary.dataPoints.recordCount !== undefined && (
                <p className={styles.emptyText}>
                  当前记录 {summary.dataPoints.recordCount} 条
                  {summary.dataPoints.minRequired ? `，至少需要 ${summary.dataPoints.minRequired} 条` : ''}
                </p>
              )}
            </div>
          )}

          {content && generationStatus === 'ready' && (
            <div className={styles.feedback}>
              {feedbackSent || summary.feedback ? (
                <p className={styles.feedbackDone}>
                  已收到你的反馈，感谢！我们会据此优化提示与调权策略。
                </p>
              ) : (
                <>
                  <p className={styles.feedbackTitle}>这份复盘准不准、有没有用？</p>
                  <div className={styles.ratingRow}>
                    {RATING_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        className={`${styles.ratingBtn} ${rating === opt.value ? styles.ratingActive : ''}`}
                        onClick={() => setRating(opt.value)}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    className={styles.reasonInput}
                    value={reason}
                    maxLength={100}
                    placeholder="哪里不准？说说原因（可选，≤100 字）"
                    onChange={(e) => setReason(e.target.value)}
                  />
                  <button
                    type="button"
                    className={styles.submitBtn}
                    disabled={rating === null || submitting}
                    onClick={handleSubmitFeedback}
                  >
                    {submitting ? '提交中…' : '提交反馈'}
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

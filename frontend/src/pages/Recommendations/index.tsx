import { useCallback, useEffect, useRef, useState } from 'react'
import styles from './index.module.css'
import {
  createRecommendation,
  getRecommendation,
  isRecommendationTerminal,
  listRecommendations,
  submitRecommendationFeedback,
} from '../../services/recommendations'
import { subjectLabels } from '../../styles/theme'
import type { Rating, Recommendation, Subject } from '../../types/api'

const SUBJECTS: Subject[] = [
  'chinese', 'math', 'english', 'physics', 'chemistry',
  'biology', 'history', 'geography', 'politics', 'other',
]

const RATING_OPTIONS: { value: Rating; label: string }[] = [
  { value: 'useful', label: '有用' },
  { value: 'neutral', label: '一般' },
  { value: 'not_useful', label: '没用' },
]

interface FeedbackDraft {
  rating: Rating | null
  reason: string
  sent: boolean
}

function formatTime(iso: string | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${hh}:${mm}`
}

export default function RecommendationsPage() {
  const [items, setItems] = useState<Recommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  // 手动请求表单
  const [subject, setSubject] = useState<Subject>('math')
  const [recordId, setRecordId] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [polling, setPolling] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)

  // 每条建议的反馈草稿（key = recommendationId）
  const [drafts, setDrafts] = useState<Record<string, FeedbackDraft>>({})
  const [submittingId, setSubmittingId] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  const loadList = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const data = await listRecommendations({ status: 'ready', page: 1, pageSize: 20 })
      setItems(data.items)
    } catch (err) {
      setListError(err instanceof Error ? err.message : '建议列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadList()
    return () => abortRef.current?.abort()
  }, [loadList])

  const setDraft = (id: string, patch: Partial<FeedbackDraft>) => {
    setDrafts((prev) => {
      const base = prev[id] ?? { rating: null, reason: '', sent: false }
      return { ...prev, [id]: { ...base, ...patch } }
    })
  }

  const handleRequest = async () => {
    if (requesting) return
    setRequestError(null)
    setRequesting(true)
    setPolling(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const pending = await createRecommendation({
        scene: 'post_session',
        subject,
        recordId: recordId.trim() ? recordId.trim() : undefined,
      })
      // 轮询直到生成进入终态（PRD 5.3：不展示半成品）
      const maxTries = 30
      let current = await getRecommendation(pending.recommendationId, controller.signal)
      let tries = 1
      while (!isRecommendationTerminal(current.generation.status) && tries < maxTries && !controller.signal.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (controller.signal.aborted) return
        current = await getRecommendation(pending.recommendationId, controller.signal)
        tries += 1
      }
      // 新建议放到列表最前
      setItems((prev) => [current, ...prev.filter((r) => r.recommendationId !== current.recommendationId)])
      setDraft(current.recommendationId, { sent: false })
    } catch (err) {
      if (controller.signal.aborted) return
      setRequestError(err instanceof Error ? err.message : '生成失败，请稍后再试')
    } finally {
      abortRef.current = null
      setPolling(false)
      setRequesting(false)
    }
  }

  const handleFeedback = async (rec: Recommendation) => {
    const draft = drafts[rec.recommendationId]
    if (!draft?.rating || submittingId) return
    setSubmittingId(rec.recommendationId)
    try {
      await submitRecommendationFeedback(rec.recommendationId, draft.rating, draft.reason)
      setDraft(rec.recommendationId, { sent: true })
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : '反馈提交失败，请稍后再试')
    } finally {
      setSubmittingId(null)
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>个性化建议</h1>
        <p className={styles.subtitle}>基于最近的学习记录与状态评估，生成贴合你当下情况的小建议。</p>
      </header>

      <section className={styles.panel}>
        <div className={styles.requestRow}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>学科</span>
            <select
              className={styles.select}
              value={subject}
              onChange={(e) => setSubject(e.target.value as Subject)}
            >
              {SUBJECTS.map((s) => (
                <option key={s} value={s}>{subjectLabels[s] ?? s}</option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>关联记录 ID（可选）</span>
            <input
              className={styles.textInput}
              value={recordId}
              placeholder="如 r_88012"
              onChange={(e) => setRecordId(e.target.value)}
            />
          </label>
          <button
            type="button"
            className={styles.primaryBtn}
            disabled={requesting}
            onClick={handleRequest}
          >
            {requesting ? (polling ? '生成中…' : '创建中…') : '请求建议'}
          </button>
        </div>
        {requestError && <p className={styles.error}>{requestError}</p>}
      </section>

      <section className={styles.list}>
        {loading && <p className={styles.empty}>加载中…</p>}
        {!loading && listError && <p className={styles.error}>{listError}</p>}
        {!loading && !listError && items.length === 0 && (
          <p className={styles.empty}>还没有建议，先在左侧选择学科请求一条吧。</p>
        )}

        {items.map((rec) => {
          const draft = drafts[rec.recommendationId]
          const subjectLabel = rec.subject ? (subjectLabels[rec.subject] ?? rec.subject) : ''
          return (
            <article key={rec.recommendationId} className={styles.card}>
              <div className={styles.cardHead}>
                <span className={styles.subjectTag}>{subjectLabel}</span>
                <span className={styles.time}>{formatTime(rec.generation.completedAt)}</span>
                {rec.generation.status === 'failed' && (
                  <span className={styles.statusBadge}>生成失败</span>
                )}
              </div>

              {rec.generation.status === 'ready' && rec.items?.length ? (
                <div className={styles.items}>
                  {rec.items.map((item, i) => (
                    <div key={i} className={styles.item}>
                      <h3 className={styles.itemTitle}>{item.title}</h3>
                      <p className={styles.itemContent}>{item.content}</p>
                    </div>
                  ))}
                  {rec.basedOn?.explain && (
                    <p className={styles.basedOn}>依据：{rec.basedOn.explain}</p>
                  )}
                </div>
              ) : (
                <p className={styles.emptyItem}>建议生成中或不可用。</p>
              )}

              {rec.generation.status === 'ready' && (
                <div className={styles.feedback}>
                  {draft?.sent || rec.feedback ? (
                    <p className={styles.feedbackDone}>已收到你的反馈，感谢！</p>
                  ) : (
                    <>
                      <p className={styles.feedbackTitle}>这条建议准不准、有没有用？</p>
                      <div className={styles.ratingRow}>
                        {RATING_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            className={`${styles.ratingBtn} ${draft?.rating === opt.value ? styles.ratingActive : ''}`}
                            onClick={() => setDraft(rec.recommendationId, { rating: opt.value })}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      <textarea
                        className={styles.reasonInput}
                        value={draft?.reason ?? ''}
                        maxLength={100}
                        placeholder="哪里不准？说说原因（可选，≤100 字）"
                        onChange={(e) => setDraft(rec.recommendationId, { reason: e.target.value })}
                      />
                      <button
                        type="button"
                        className={styles.submitBtn}
                        disabled={!draft?.rating || submittingId === rec.recommendationId}
                        onClick={() => handleFeedback(rec)}
                      >
                        {submittingId === rec.recommendationId ? '提交中…' : '提交反馈'}
                      </button>
                    </>
                  )}
                </div>
              )}
            </article>
          )
        })}
      </section>
    </div>
  )
}

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import styles from './index.module.css'
import { subjectLabels } from '@/styles/theme'
import { getRecommendation, updateLearningRecord } from '@/services/learningRecord'
import { putRecommendationFeedback } from '@/services/feedback'
import { getPlanByDate, getPlanById, localDateString } from '@/services/plans'
import {
  computeDisplaySeconds,
  discardTimerSession,
  finishTimerSession,
  getCurrentTimerSession,
  heartbeatTimerSession,
  isCountdownReached,
  startTimerSession,
} from '@/services/timer'

const EMOTION_LABELS = { positive: '积极', neutral: '一般', negative: '消极' }
const COMPLETION_LABELS = { completed: '完成', partial: '部分完成', abandoned: '放弃' }
const RATING_LABELS = { useful: '有用', neutral: '一般', not_useful: '没用' }

/** 心跳间隔：僵尸判定阈值是 30 分钟无心跳，60s 上报有足够余量 */
const HEARTBEAT_INTERVAL_MS = 60 * 1000

function formatTime(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0))
  const m = Math.floor(s / 60)
  const rest = s % 60
  return `${String(m).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function RatingButtons({ value, onChange, options, wide = false }) {
  return (
    <div className={styles.selfOptions}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={[
            styles.selfBtn,
            wide ? styles.selfBtnWide : '',
            value === option.value ? styles.selfBtnActive : '',
          ].join(' ')}
          onClick={() => onChange(option.value)}
        >
          {option.num !== undefined && <span className={styles.selfBtnNum}>{option.num}</span>}
          <span className={styles.selfBtnLabel}>{option.label}</span>
        </button>
      ))}
    </div>
  )
}

/**
 * 收尾**层 1**（D20）：结束瞬间的 0 步卡。
 *
 * 核心改造：**从「拦截式量表」变「非拦截式轻卡」——结束动作本身不拦。**
 * 到这里记录已经落库了，用户可以直接走（[完成 ✓]），也可以花 10 秒补两句。
 * 这正是 D15「记录是活实体、可事后回写」在 UI 上的样子。
 */
function SettleCard({ subjectLabel, minutes, onDone, onRefine }) {
  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>本次已记录</span>
        <span className={styles.popText}>
          {subjectLabel} · {minutes} 分钟
        </span>
      </div>
      <div className={styles.settleMeta}>
        已经帮你留下来了。想补两句就展开，不想就收起来——之后随时能补。
      </div>
      <div className={styles.popActions}>
        <button type="button" className={styles.popOk} onClick={onDone}>完成 ✓</button>
        <button type="button" className={styles.popRestart} onClick={onRefine}>再说两句</button>
      </div>
    </>
  )
}

/**
 * 收尾**层 2**（D20）：轻收尾卡，约 10 秒。
 *
 * - **完成度**：唯一"半强制"的问句（三选一，直填）；
 * - **一句感受**：叙事轨，可选。写进 note；
 * - **情绪快捷词**：可选兜底（非 1–5 刻度）。
 *
 * ⚠️ **专注 / 疲劳 / 难度不在这里问**——目标态 §3.7(a) 定的是"由模型从一句感受转译"，
 * 那是 B 板块的口语转译（D34）。转译接上之前这三个字段**留空**，
 * 由服务端按"软字段缺失 → 跳过并按可用部分归一化"处理。**不造数**。
 */
function LightSettleCard({ completion, setCompletion, note, setNote, emotion, setEmotion,
                           saving, error, onSave, onSkip }) {
  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>再补两句？</span>
        <span className={styles.popText}>都可以跳过</span>
      </div>

      <div className={styles.selfSection}>
        <span className={styles.selfLabel}>完成情况</span>
        <RatingButtons
          value={completion}
          onChange={setCompletion}
          wide
          options={['completed', 'partial', 'abandoned'].map((c) => ({
            value: c,
            label: COMPLETION_LABELS[c],
          }))}
        />
      </div>

      <div className={styles.selfSection}>
        <span className={styles.selfLabel}>一句感受</span>
        <textarea
          className={styles.noteInput}
          value={note}
          maxLength={100}
          rows={2}
          placeholder="卡在哪、哪句没看懂…（可不写）"
          onChange={(e) => setNote(e.target.value)}
        />
      </div>

      <div className={styles.selfSection}>
        <span className={styles.selfLabel}>情绪</span>
        <RatingButtons
          value={emotion}
          onChange={setEmotion}
          wide
          options={['positive', 'neutral', 'negative'].map((e) => ({
            value: e,
            label: EMOTION_LABELS[e],
          }))}
        />
      </div>

      <div className={styles.hintLine}>
        正确率和错题不急着现在填——之后在记录里随时能补。
      </div>

      {error && <div className={styles.popError}>{error}</div>}

      <div className={styles.popActions}>
        <button type="button" className={styles.popOk} disabled={saving} onClick={onSave}>
          {saving ? '保存中…' : '保存'}
        </button>
        <button type="button" className={styles.popRestart} onClick={onSkip}>跳过</button>
      </div>
    </>
  )
}

/**
 * 恢复裁决卡（D31）。**不自动记账**——僵尸会话最怕的就是系统替用户编一段时长。
 * 三态：保留按 X 记 / 手动改时长 / 丢弃。
 */
function VerdictCard({ restore, subjectLabel, saving, error, onKeep, onManual, onDiscard }) {
  const [manual, setManual] = useState(String(restore?.suggestedMinutes ?? 25))
  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>上次计时没正常结束</span>
        <span className={styles.popText}>{subjectLabel}</span>
      </div>
      <div className={styles.settleMeta}>
        这个会话中途断了（关页面或长时间没操作）。已计{' '}
        <strong>{restore?.suggestedMinutes ?? '—'}</strong> 分钟。
        系统不会替你记时长——你说记多少就记多少。
      </div>

      <div className={styles.verdictManual}>
        <span className={styles.durationLabel}>改成</span>
        <input
          className={styles.durationInput}
          type="number"
          min={1}
          max={600}
          value={manual}
          onChange={(e) => setManual(e.target.value)}
        />
        <span className={styles.durationUnit}>分</span>
      </div>

      {error && <div className={styles.popError}>{error}</div>}

      <div className={styles.verdictActions}>
        <button type="button" className={styles.popOk} disabled={saving}
                onClick={() => onKeep(restore?.suggestedMinutes ?? 1)}>
          保留按 {restore?.suggestedMinutes ?? 1} 分钟记
        </button>
        <button type="button" className={styles.popRestart} disabled={saving}
                onClick={() => onManual(Number(manual) || 1)}>
          按我改的记
        </button>
        <button type="button" className={styles.popRestart} disabled={saving} onClick={onDiscard}>
          丢弃（不记）
        </button>
      </div>
    </>
  )
}

function RecommendationPanel({ recommendation, onOk, onRestart }) {
  const [feedbackRating, setFeedbackRating] = useState(null)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [feedbackError, setFeedbackError] = useState(null)

  const status = recommendation?.generation?.status
  const items = recommendation?.items
  const recId = recommendation?.recommendationId
  const existingFeedback = recommendation?.feedback
  const showFeedback = status === 'ready' && items && items.length > 0 && recId

  const handleFeedback = async (rating) => {
    if (!recId || feedbackSent) return
    setFeedbackRating(rating)
    setFeedbackError(null)
    try {
      await putRecommendationFeedback(recId, rating)
      setFeedbackSent(true)
    } catch {
      setFeedbackError('反馈提交失败')
      setFeedbackRating(null)
    }
  }

  let body
  if (status === 'ready' && items && items.length > 0) {
    body = (
      <>
        <div className={styles.recList}>
          {items.map((item, index) => (
            <div key={index} className={styles.recItem}>
              <div className={styles.recTitle}>{item.title}</div>
              <div className={styles.recContent}>{item.content}</div>
            </div>
          ))}
        </div>
        {showFeedback && (
          <div className={styles.feedbackSection}>
            <span className={styles.feedbackLabel}>
              {existingFeedback
                ? '已收到你的评价'
                : feedbackSent
                  ? '感谢反馈'
                  : '这些建议对你有帮助吗？'}
            </span>
            {!existingFeedback && !feedbackSent && (
              <div className={styles.feedbackRow}>
                {['useful', 'neutral', 'not_useful'].map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={[
                      styles.feedbackBtn,
                      feedbackRating === r ? styles.feedbackBtnActive : '',
                    ].join(' ')}
                    onClick={() => handleFeedback(r)}
                  >
                    {RATING_LABELS[r]}
                  </button>
                ))}
              </div>
            )}
            {feedbackError && <div className={styles.popError}>{feedbackError}</div>}
          </div>
        )}
      </>
    )
  } else if (status === 'insufficient_data') {
    body = (
      <div className={styles.recHint}>
        这次的数据还比较少，多记录几次，就能给你更贴心的建议啦。
      </div>
    )
  } else if (status === 'failed') {
    body = (
      <div className={styles.recHint}>
        建议生成失败了，先休息一下吧，下次再试试。
      </div>
    )
  } else {
    body = <div className={styles.recHint}>本次学习记录已保存。</div>
  }

  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>学习小结</span>
        <span className={styles.popText}>已经帮你记下这次专注</span>
      </div>
      {body}
      <div className={styles.popActions}>
        <button type="button" className={styles.popOk} onClick={onOk}>完成</button>
        <button type="button" className={styles.popRestart} onClick={onRestart}>再学一轮</button>
      </div>
    </>
  )
}

export default function StudyTimerPage() {
  const FALLBACK_TASK = '今日学习（待编辑）'

  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // ---------------------------------------------------------------------------
  // 上下文来源：**URL query 自取，不再依赖 navigate(state)**
  //
  // 技术债「/study-timer 刷新丢上下文」的根因就是靠 location.state 传参——
  // 刷新/直链进来 state 为空，任务、时长、planId 全丢。
  // 现在 query 承载上下文（可刷新、可分享、可直链），会话本身则由服务端持久化。
  // ---------------------------------------------------------------------------
  const queryPlanId = searchParams.get('planId')
  const queryTaskId = searchParams.get('taskId')
  const queryMinutes = Number(searchParams.get('minutes')) || null
  const querySubject = searchParams.get('subject')

  const [booting, setBooting] = useState(true)
  const [session, setSession] = useState(null)
  const [restore, setRestore] = useState(null)

  // 开始面板的参数（无进行中会话时用）
  const [task, setTask] = useState(FALLBACK_TASK)
  const [taskId, setTaskId] = useState(queryTaskId || null)
  const [planId, setPlanId] = useState(queryPlanId || null)
  const [subject, setSubject] = useState(querySubject || 'SX')
  const [mode, setMode] = useState('countdown')
  const [targetMinutes, setTargetMinutes] = useState(queryMinutes || 25)
  const [startError, setStartError] = useState(null)

  // 本地暂停（服务端没有挂起语义：只留「结束」一个出口）
  const [paused, setPaused] = useState(false)
  const pausedRef = useRef({ pausedAt: null, accumulatedMs: 0 })

  const [now, setNow] = useState(() => Date.now())
  const [stage, setStage] = useState('idle') // idle | settle | light | polling | summary | verdict
  const [record, setRecord] = useState(null)
  const [completion, setCompletion] = useState('completed')
  const [note, setNote] = useState('')
  const [emotion, setEmotion] = useState(null)
  const [busy, setBusy] = useState(false)
  const [popupError, setPopupError] = useState(null)
  const [recId, setRecId] = useState(null)
  const [recReady, setRecReady] = useState(false)
  const [recommendation, setRecommendation] = useState(null)
  const [planTaskStats, setPlanTaskStats] = useState({ completed: 0, total: 0 })

  // `now` 每秒更新，暂停时长自动跟着重算（暂停中也在涨）
  const pausedSeconds = useMemo(() => {
    const { pausedAt, accumulatedMs } = pausedRef.current
    const extra = pausedAt ? Date.now() - pausedAt : 0
    return (accumulatedMs + extra) / 1000
  }, [now])

  const display = useMemo(() => {
    if (!session) return { remaining: null, elapsed: 0 }
    return computeDisplaySeconds(session, now, pausedSeconds)
  }, [session, now, pausedSeconds])

  const reachedTarget = session ? isCountdownReached(session, display.elapsed) : false
  const subjectLabel = subjectLabels[session?.subject || subject] ?? (session?.subject || subject)

  // ---------------------------------------------------------------------------
  // 每秒 tick：只驱动显示，不递减任何本地状态
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  // ---------------------------------------------------------------------------
  // 进入页面：先问服务端"现在有没有进行中的会话"
  // ---------------------------------------------------------------------------
  const refreshStats = useCallback(async () => {
    const plan = await getPlanByDate(localDateString())
    const tasks = plan?.tasks || []
    setPlanTaskStats({
      completed: tasks.filter((t) => t.status === 'completed').length,
      total: tasks.length,
    })
  }, [])

  const loadCurrent = useCallback(async () => {
    try {
      const current = await getCurrentTimerSession()
      if (current?.active && current.session) {
        setSession(current.session)
        setRestore(current.restore || null)
        if (current.restore?.needsVerdict) setStage('verdict')
        else setStage('idle')
      } else {
        setSession(null)
        setRestore(null)
        setStage('idle')
      }
    } catch {
      // 拉不到就按"没有会话"处理：不阻塞用户手动开始
      setSession(null)
      setRestore(null)
    } finally {
      setBooting(false)
    }
  }, [])

  useEffect(() => {
    loadCurrent()
    refreshStats().catch(() => {})
  }, [loadCurrent, refreshStats])

  // 补齐任务文案：**只解析一次**。
  //
  // 为什么在"有会话"时也要跑：刷新回来时 session 是从服务端恢复的，而任务文案是本页
  // 从计划里查出来的展示信息——不查就只能显示兜底文案，用户看不出自己在学什么。
  // 优先用会话自带的 planId/taskId（服务端记录的那次），没有才用 query。
  const contextResolvedRef = useRef(false)
  useEffect(() => {
    if (booting || contextResolvedRef.current) return
    const pid = session?.planId || queryPlanId
    const tid = session?.taskId || queryTaskId
    if (!pid && !tid) {
      contextResolvedRef.current = true
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const plan = pid ? await getPlanById(pid) : await getPlanByDate(localDateString())
        if (cancelled || !plan) return
        const target = tid
          ? (plan.tasks || []).find((t) => t.taskId === tid)
          : (plan.tasks || [])[0]
        if (target) {
          const label = subjectLabels[target.subject] ?? target.subject
          setTask(`${label} · ${target.topic}`)
        }
        // 开始面板的默认值只在"还没有会话"时设——别覆盖正在进行的会话参数
        if (!session) {
          setPlanId(plan.planId)
          if (target) {
            setTaskId(target.taskId)
            if (!querySubject && target.subject) setSubject(target.subject)
            if (!queryMinutes && target.estimatedMinutes) setTargetMinutes(target.estimatedMinutes)
          }
        }
      } catch {
        // 拉计划失败不阻塞：任务文案退回兜底，用户仍可开始计时
      } finally {
        contextResolvedRef.current = true
      }
    })()
    return () => { cancelled = true }
  }, [booting, session, queryPlanId, queryTaskId, queryMinutes, querySubject])

  // ---------------------------------------------------------------------------
  // 心跳：僵尸判定的唯一依据。不刷新心跳的后果不是报错，而是下次回来被判异常会话。
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!session || session.status !== 'running' || paused) return
    const id = setInterval(() => {
      heartbeatTimerSession(session.sessionId).catch(() => {})
    }, HEARTBEAT_INTERVAL_MS)
    return () => clearInterval(id)
  }, [session, paused])

  // 建议轮询
  useEffect(() => {
    if (!recId) return
    let cancelled = false
    let timer = null

    const poll = async () => {
      try {
        const result = await getRecommendation(recId)
        if (cancelled) return
        if (result.generation?.status === 'pending') return
        if (timer) clearInterval(timer)
        setRecommendation(result)
        setRecReady(true)
        // ⚠️ 只有不在收尾卡阶段时才自动前进：否则建议生成得够快时，
        // 「本次已记录」那张卡会被小结面板直接顶掉，用户根本没机会看一眼。
        setStage((prev) => (prev === 'settle' || prev === 'light' ? prev : 'summary'))
      } catch {
        if (cancelled) return
        if (timer) clearInterval(timer)
        setRecommendation(null)
        setPopupError('获取建议失败，请稍后再试')
        setRecReady(true)
        setStage((prev) => (prev === 'settle' || prev === 'light' ? prev : 'summary'))
      }
    }

    poll()
    timer = setInterval(poll, 2000)
    return () => {
      cancelled = true
      if (timer) clearInterval(timer)
    }
  }, [recId])

  // ---------------------------------------------------------------------------
  // 开始 / 暂停 / 结束
  // ---------------------------------------------------------------------------
  const handleStart = async () => {
    setStartError(null)
    setBusy(true)
    try {
      const created = await startTimerSession({
        mode,
        ...(mode === 'countdown' ? { targetMinutes } : {}),
        ...(planId ? { planId } : {}),
        ...(taskId ? { taskId } : {}),
        subject,
      })
      pausedRef.current = { pausedAt: null, accumulatedMs: 0 }
      setPaused(false)
      setSession(created)
      setRestore(null)
      setNow(Date.now())
      setStage('idle')
    } catch (err) {
      if (err?.status === 409) {
        // 已有进行中的会话：重新拉一次，让用户看到它并做处置（不静默接管）
        setStartError('已有一个进行中的计时，先处理它再开始新的')
        await loadCurrent()
      } else {
        setStartError('开始计时失败，请稍后再试')
      }
    } finally {
      setBusy(false)
    }
  }

  const handlePauseToggle = () => {
    if (paused) {
      // 恢复：把这段暂停累计进去
      const { pausedAt, accumulatedMs } = pausedRef.current
      pausedRef.current = {
        pausedAt: null,
        accumulatedMs: accumulatedMs + (pausedAt ? Date.now() - pausedAt : 0),
      }
      setPaused(false)
      heartbeatTimerSession(session.sessionId).catch(() => {})
    } else {
      pausedRef.current = { ...pausedRef.current, pausedAt: Date.now() }
      setPaused(true)
    }
    setNow(Date.now())
  }

  /**
   * 结束 → 收尾层 1。
   *
   * 时长口径：
   * - **有过暂停** → 显式传 durationMinutes（服务端不知道前端暂停了多久），
   *   倒计时还要按 target 封顶；
   * - **没暂停** → 不传，让服务端按 mode 算（封顶逻辑在服务端更可靠）。
   */
  const handleFinish = async () => {
    if (!session) return
    setBusy(true)
    setPopupError(null)
    const hadPause = pausedRef.current.accumulatedMs > 0 || pausedRef.current.pausedAt
    let durationMinutes
    if (hadPause) {
      const elapsed = display.elapsed
      const capped = session.mode === 'countdown'
        ? Math.min(elapsed, (session.targetMinutes ?? 0) * 60)
        : elapsed
      durationMinutes = Math.max(1, Math.round(capped / 60))
    }
    try {
      const created = await finishTimerSession(session.sessionId, {
        completion: 'completed',
        ...(durationMinutes ? { durationMinutes } : {}),
      })
      setRecord(created)
      setCompletion('completed')
      setNote('')
      setEmotion(null)
      setSession(null)
      setRestore(null)
      pausedRef.current = { pausedAt: null, accumulatedMs: 0 }
      setPaused(false)
      setStage('settle')
      refreshStats().catch(() => {})
      if (created.recommendation?.recommendationId) {
        setRecReady(false)
        setRecId(created.recommendation.recommendationId)
      }
    } catch (err) {
      // 异常会话必须由用户裁决，不能自动记账（D31）
      if (err?.status === 400 && err?.field === 'durationMinutes') {
        await loadCurrent()
        setStage('verdict')
      } else {
        setPopupError('结束失败，请稍后再试')
      }
    } finally {
      setBusy(false)
    }
  }

  /** 收尾卡之后去哪：建议好了直接看小结；没好去轮询；压根没建议就直接小结 */
  const advanceAfterSettle = useCallback(() => {
    if (!recId) {
      setStage('summary')
      return
    }
    setStage(recReady ? 'summary' : 'polling')
  }, [recId, recReady])

  /** 收尾层 2 保存：**回写**那条已经落库的记录（D15） */
  const handleSaveLight = async () => {
    if (!record) return
    setBusy(true)
    setPopupError(null)
    try {
      await updateLearningRecord(record.recordId, {
        completion,
        ...(note.trim() ? { note: note.trim() } : {}),
        ...(emotion ? { selfReport: { emotion } } : {}),
      })
      advanceAfterSettle()
    } catch {
      setPopupError('保存失败，请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  const closePopup = () => {
    setStage('idle')
    setRecord(null)
    setRecId(null)
    setRecReady(false)
    setRecommendation(null)
    setPopupError(null)
  }

  const handleSettleDone = () => {
    // 用户直接走人：建议还在生成就让它后台跑，不拦着
    advanceAfterSettle()
  }

  // ---------------------------------------------------------------------------
  // 裁决卡三态（D31）
  // ---------------------------------------------------------------------------
  const handleVerdictFinish = async (minutes) => {
    setBusy(true)
    setPopupError(null)
    try {
      const created = await finishTimerSession(session.sessionId, {
        completion: 'completed',
        durationMinutes: minutes,
      })
      setRecord(created)
      setSession(null)
      setRestore(null)
      setStage('settle')
      refreshStats().catch(() => {})
      if (created.recommendation?.recommendationId) {
        setRecReady(false)
        setRecId(created.recommendation.recommendationId)
      }
    } catch {
      setPopupError('处理失败，请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  const handleVerdictDiscard = async () => {
    setBusy(true)
    setPopupError(null)
    try {
      await discardTimerSession(session.sessionId)
      setSession(null)
      setRestore(null)
      setStage('idle')
    } catch {
      setPopupError('丢弃失败，请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 渲染
  // ---------------------------------------------------------------------------
  const showPopup = ['settle', 'light', 'polling', 'summary', 'verdict'].includes(stage)

  if (booting) {
    return (
      <div className={styles.app}>
        <div className={styles.bgSky} aria-hidden="true" />
        <main className={styles.centerStage}>
          <h1 className={styles.epochx}>EpochX</h1>
          <div className={styles.recHint}>正在读取计时状态…</div>
        </main>
      </div>
    )
  }

  return (
    <div className={styles.app}>
      <div className={styles.bgSky} aria-hidden="true" />

      <header className={styles.topbar}>
        <img className={styles.brandLogo} src="/brand/logo-full-on-light.png" alt="logo" />

        <div className={styles.taskInline}>
          <div className={styles.taskView}>
            <span className={styles.taskLabel}>任务</span>
            <span className={styles.taskTitle}>{session ? (task || FALLBACK_TASK) : task}</span>
          </div>
        </div>

        <label className={styles.subjectField}>
          <span className={styles.subjectLabel}>学科</span>
          <select
            className={styles.subjectSelect}
            value={session?.subject || subject}
            disabled={Boolean(session)}
            onChange={(e) => setSubject(e.target.value)}
          >
            {Object.entries(subjectLabels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </label>

        <div className={styles.modeTabs}>
          <button
            className={`${styles.modeTab} ${(session?.mode || mode) === 'countdown' ? styles.active : ''}`}
            disabled={Boolean(session)}
            onClick={() => setMode('countdown')}
          >
            倒计时
          </button>
          <button
            className={`${styles.modeTab} ${(session?.mode || mode) === 'countup' ? styles.active : ''}`}
            disabled={Boolean(session)}
            onClick={() => setMode('countup')}
          >
            正计时
          </button>
        </div>

        {!session && mode === 'countdown' && (
          <label className={styles.durationField}>
            <span className={styles.durationLabel}>目标</span>
            <input
              className={styles.durationInput}
              type="number"
              min={1}
              max={600}
              value={targetMinutes}
              onChange={(e) => setTargetMinutes(Math.max(1, Math.min(600, Number(e.target.value) || 1)))}
            />
            <span className={styles.durationUnit}>分</span>
          </label>
        )}

        <span className={styles.timeBig}>
          {session
            ? formatTime(display.remaining !== null ? display.remaining : display.elapsed)
            : formatTime((mode === 'countdown' ? targetMinutes : 0) * 60)}
        </span>
        {paused && <span className={styles.pausedTag}>已暂停</span>}

        <div className={styles.controls}>
          {!session ? (
            <button className={`${styles.btn} ${styles.primary}`} disabled={busy} onClick={handleStart}>
              开始
            </button>
          ) : (
            <>
              <button className={`${styles.btn} ${styles.ghost}`} onClick={handlePauseToggle}>
                {paused ? '继续' : '暂停'}
              </button>
              <button className={`${styles.btn} ${styles.primary}`} disabled={busy} onClick={handleFinish}>
                结束
              </button>
            </>
          )}
        </div>
      </header>

      <main className={styles.centerStage}>
        <h1 className={styles.epochx}>EpochX</h1>
        {!session && (
          <div className={styles.idleHint}>
            {mode === 'countdown'
              ? `目标 ${targetMinutes} 分钟 · 到点只是提醒，不会自动结束`
              : '正计时不限时，随时可以结束'}
          </div>
        )}
        {session && reachedTarget && !paused && (
          <div className={styles.idleHint}>到点了 · 可以结束，也可以继续（继续的部分照常计入）</div>
        )}
        {startError && <div className={styles.popError}>{startError}</div>}
      </main>

      {showPopup && (
        <div className={styles.completionPop}>
          {stage === 'verdict' && (
            <VerdictCard
              restore={restore}
              subjectLabel={subjectLabel}
              saving={busy}
              error={popupError}
              onKeep={handleVerdictFinish}
              onManual={handleVerdictFinish}
              onDiscard={handleVerdictDiscard}
            />
          )}
          {stage === 'settle' && record && (
            <SettleCard
              subjectLabel={subjectLabels[record.subject] ?? record.subject}
              minutes={record.durationMinutes}
              onDone={handleSettleDone}
              onRefine={() => setStage('light')}
            />
          )}
          {stage === 'light' && (
            <LightSettleCard
              completion={completion}
              setCompletion={setCompletion}
              note={note}
              setNote={setNote}
              emotion={emotion}
              setEmotion={setEmotion}
              saving={busy}
              error={popupError}
              onSave={handleSaveLight}
              onSkip={advanceAfterSettle}
            />
          )}
          {stage === 'polling' && <div className={styles.popLoading}>正在生成学习建议…</div>}
          {stage === 'summary' && (
            <RecommendationPanel
              recommendation={recommendation}
              onOk={closePopup}
              onRestart={() => { closePopup(); navigate('/study-timer', { replace: true }) }}
            />
          )}
        </div>
      )}
    </div>
  )
}

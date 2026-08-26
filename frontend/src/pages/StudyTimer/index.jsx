import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import styles from './index.module.css'
import { subjectLabels } from '@/styles/theme'
import { createLearningRecord, getRecommendation } from '@/services/learningRecord'
import { putRecommendationFeedback } from '@/services/feedback'
import { getPlanByDate, localDateString } from '@/services/plans'

const FOCUS_LABELS = { 1: '分心', 2: '一般', 3: '还好', 4: '专注', 5: '非常专注' }
const FATIGUE_LABELS = { 1: '精神', 2: '轻微', 3: '一般', 4: '疲劳', 5: '非常疲劳' }
const EMOTION_LABELS = { positive: '积极', neutral: '一般', negative: '消极' }
const DIFFICULTY_LABELS = { easy: '简单', moderate: '适中', hard: '困难' }
const COMPLETION_LABELS = { completed: '完成', partial: '部分完成', abandoned: '放弃' }
const RATING_LABELS = { useful: '有用', neutral: '一般', not_useful: '没用' }

function formatTime(totalSeconds) {
  if (totalSeconds <= 0) return '00:00'
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function DurationField({ label, value, min, max, onCommit }) {
  const [draft, setDraft] = useState(String(value))

  const commit = () => {
    let n = parseInt(draft, 10)
    if (Number.isNaN(n)) n = value
    n = Math.min(max, Math.max(min, n))
    setDraft(String(n))
    onCommit(n)
  }

  return (
    <label className={styles.durationField}>
      <span className={styles.durationLabel}>{label}</span>
      <input
        className={styles.durationInput}
        type="number"
        min={min}
        max={max}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
      />
      <span className={styles.durationUnit}>分</span>
    </label>
  )
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

function SelfAssessment({ task, error, planTaskStats, onConfirm, onSkip }) {
  const [completion, setCompletion] = useState('completed')
  const [focus, setFocus] = useState(null)
  const [fatigue, setFatigue] = useState(null)
  const [emotion, setEmotion] = useState(null)
  const [difficultyFeel, setDifficultyFeel] = useState(null)

  const complete = focus !== null && fatigue !== null && emotion !== null && difficultyFeel !== null

  const submit = () => {
    if (!complete) return
    onConfirm({ focus, fatigue, emotion, difficultyFeel, completion })
  }

  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>任务完成</span>
        <span className={styles.popText}>「{task}」已完成</span>
      </div>

      {/* 今日计划完成计数（PRD 5.3：让用户感知"今天做完了几个"） */}
      {planTaskStats && planTaskStats.total > 0 && (
        <div className={styles.planStats}>
          今日已完成
          <strong className={styles.planStatsNum}>
            {planTaskStats.completed} / {planTaskStats.total}
          </strong>
          个计划任务
        </div>
      )}

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
        <span className={styles.selfLabel}>专注度</span>
        <RatingButtons
          value={focus}
          onChange={setFocus}
          options={[1, 2, 3, 4, 5].map((n) => ({ value: n, num: n, label: FOCUS_LABELS[n] }))}
        />
      </div>

      <div className={styles.selfSection}>
        <span className={styles.selfLabel}>疲劳度</span>
        <RatingButtons
          value={fatigue}
          onChange={setFatigue}
          options={[1, 2, 3, 4, 5].map((n) => ({ value: n, num: n, label: FATIGUE_LABELS[n] }))}
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

      <div className={styles.selfSection}>
        <span className={styles.selfLabel}>难度感受</span>
        <RatingButtons
          value={difficultyFeel}
          onChange={setDifficultyFeel}
          wide
          options={['easy', 'moderate', 'hard'].map((d) => ({
            value: d,
            label: DIFFICULTY_LABELS[d],
          }))}
        />
      </div>

      {error && <div className={styles.popError}>{error}</div>}

      <div className={styles.popActions}>
        <button
          type="button"
          className={styles.popOk}
          disabled={!complete}
          onClick={submit}
        >
          提交记录
        </button>
        <button type="button" className={styles.popRestart} onClick={onSkip}>
          跳过
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
  // 兜底文案：未读到当日计划时使用，避免空白任务显示
  const FALLBACK_TASK = '今日学习（待编辑）'

  // 接 location.state：StudyPlanEditor / StudyGuide 点「进入」时透传。
  // - availableMinutes：覆盖默认 25 分钟（计划设了 60，番茄钟就该是 60）
  // - task：覆盖 fallback 任务（用户输入的主题或规则引擎推荐）
  // - subject：与任务配套
  // 直接访问 /study-timer 路由时 state 为空，保留原默认值 25 + FALLBACK_TASK
  const location = useLocation()
  const navState = location.state || {}
  const initialMinutes = Number.isInteger(navState.availableMinutes) && navState.availableMinutes > 0
    ? navState.availableMinutes
    : 25

  const [task, setTask] = useState(navState.task || FALLBACK_TASK)
  const [taskSource, setTaskSource] = useState(navState.task ? 'plan' : 'fallback') // 'plan' | 'edited' | 'fallback'
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(navState.task || FALLBACK_TASK)

  // 学科默认值：state 透传 > 任务字符串解析（如「数学 · 函数与导数 · 巩固」前缀）
  // 解析不到时维持 math
  const initialSubject = (() => {
    if (typeof navState.subject === 'string' && navState.subject) return navState.subject
    const t = navState.task
    if (typeof t === 'string') {
      const hit = Object.entries(subjectLabels).find(([, label]) => t.startsWith(`${label} ·`))
      if (hit) return hit[0]
    }
    return 'SX'
  })()
  const [subject, setSubject] = useState(initialSubject)

  const [mode, setMode] = useState('focus')
  // 关键：focusMinutes 默认值改为 state 透传的可用分钟（PRD 5.1：计划与执行端一致）
  const [focusMinutes, setFocusMinutes] = useState(initialMinutes)
  const [breakMinutes, setBreakMinutes] = useState(5)
  const [remaining, setRemaining] = useState(initialMinutes * 60)
  const [isRunning, setIsRunning] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [sessionStart, setSessionStart] = useState(null)

  // 标记：state 透传时跳过 useEffect 拉 plan（任务已确定，避免 100% 重复拉取）
  const skipPlanFetch = Boolean(navState.task && navState.availableMinutes)

  const [popupPhase, setPopupPhase] = useState('selfAssessment')
  const [recId, setRecId] = useState(null)
  const [recommendation, setRecommendation] = useState(null)
  const [popupError, setPopupError] = useState(null)

  // 今日计划完成计数（PRD 5.3：完成弹窗里展示「今日已完成 N / M」）
  // mount 拉一次，自评提交成功后拉一次
  const [planTaskStats, setPlanTaskStats] = useState({ completed: 0, total: 0 })

  // 当前正在执行的计划任务 ID（用于提交学习记录时关联计划任务，驱动状态更新和 AI 上下文）
  const [planTaskId, setPlanTaskId] = useState(null)
  const [planId, setPlanId] = useState(navState.planId || null)

  const timerRef = useRef(null)

  const totalSeconds = (mode === 'focus' ? focusMinutes : breakMinutes) * 60

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setIsRunning(false)
  }, [])

  const startTimer = useCallback(() => {
    if (totalSeconds <= 0) return
    if (timerRef.current) return
    setIsRunning(true)
    timerRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current)
          timerRef.current = null
          setIsRunning(false)
          if (mode === 'focus') {
            setShowDone(true)
            setPopupPhase('selfAssessment')
            setRecId(null)
            setRecommendation(null)
            setPopupError(null)
          }
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }, [mode, totalSeconds])

  useEffect(() => {
    stopTimer()
    setRemaining(totalSeconds)
  }, [mode, totalSeconds, stopTimer])

  // 挂载时拉取今日 plan 的所有 tasks 算完成计数（弹窗展示用）
  // 不依赖 skipPlanFetch（state 透传时也要统计展示）
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const plan = await getPlanByDate(localDateString())
      if (cancelled) return
      const tasks = plan?.tasks || []
      const completed = tasks.filter((t) => t.status === 'completed').length
      setPlanTaskStats({ completed, total: tasks.length })
    })()
    return () => { cancelled = true }
  }, [])

  // 提交自评后刷新计数（PRD 5.3：完成弹窗展示「今日已完成 N/M」实时数）
  const refreshPlanStats = useCallback(async () => {
    const plan = await getPlanByDate(localDateString())
    const tasks = plan?.tasks || []
    setPlanTaskStats({
      completed: tasks.filter((t) => t.status === 'completed').length,
      total: tasks.length,
    })
  }, [])

  // 挂载时拉取当日计划的第一条任务作为默认学习任务。
  // - 命中 → 用「学科 · 方向」做默认文案，并把学科选项切到对应 subject
  // - 未命中或网络异常 → 保留 FALLBACK_TASK，不阻塞计时主流程
  // - 透传 state 时跳过：任务/学科已从 location.state 取到
  useEffect(() => {
    if (skipPlanFetch) return
    let cancelled = false
    ;(async () => {
      const plan = await getPlanByDate(localDateString())
      if (cancelled) return
      const first = plan?.tasks?.[0]
      if (!first) return
      const subjectLabel = subjectLabels[first.subject] ?? first.subject
      const next = `${subjectLabel} · ${first.topic}`
      setTask(next)
      setDraft(next)
      setTaskSource('plan')
      if (first.subject) setSubject(first.subject)
      setPlanTaskId(first.taskId)
      setPlanId(plan.planId)
    })()
    return () => {
      cancelled = true
    }
  }, [skipPlanFetch])

  // 从 StudyPlanEditor/StudyGuide 透传进入时，已有 planId 但没有 taskId，
  // 需查计划获取首条任务的 taskId（用于提交学习记录时关联计划任务）
  useEffect(() => {
    if (!skipPlanFetch || !navState.planId) return
    let cancelled = false
    ;(async () => {
      const plan = await getPlanByDate(localDateString())
      if (cancelled) return
      setPlanId(plan.planId)
      const first = plan?.tasks?.[0]
      if (first) setPlanTaskId(first.taskId)
    })()
    return () => { cancelled = true }
  }, [skipPlanFetch, navState.planId])

  useEffect(() => {
    if (!recId) return
    let cancelled = false
    let timer = null

    const poll = async () => {
      try {
        const result = await getRecommendation(recId)
        if (cancelled) return
        const status = result.generation?.status
        if (status === 'pending') return
        if (timer) clearInterval(timer)
        setRecommendation(result)
        setPopupPhase('recommendation')
      } catch {
        if (cancelled) return
        if (timer) clearInterval(timer)
        setRecommendation(null)
        setPopupError('获取建议失败，请稍后再试')
        setPopupPhase('recommendation')
      }
    }

    poll()
    timer = setInterval(poll, 2000)

    return () => {
      cancelled = true
      if (timer) clearInterval(timer)
    }
  }, [recId])

  const resetPopup = () => {
    setShowDone(false)
    setPopupPhase('selfAssessment')
    setRecId(null)
    setRecommendation(null)
    setPopupError(null)
  }

  const handleConfirmSelfReport = async (payload) => {
    const { completion, ...selfReport } = payload
    setPopupPhase('submitting')
    setPopupError(null)
    try {
      // 用「实际跑过的秒数」向上取整到分钟，不复用预设的 focusMinutes；
      // 否则用户跑 1:29 也会被记成"预设 25 分钟"，与实际偏差高达 20+ 分钟。
      const actualSeconds = Math.max(0, totalSeconds - remaining)
      const actualMinutes = Math.max(1, Math.ceil(actualSeconds / 60))
      const result = await createLearningRecord({
        subject,
        startedAt: sessionStart || new Date(Date.now() - actualSeconds * 1000).toISOString(),
        durationMinutes: actualMinutes,
        behavior: { completion },
        selfReport,
        planTaskId,
      })

      // 刷新今日计划完成计数（PRD 5.3：弹窗里展示「今日已完成 N/M」）
      // 在设置 recId 之前先调，让弹窗切到 recommendation 前数据已就绪
      refreshPlanStats().catch(() => {}); // 失败不影响主流程

      if (result.recommendation?.recommendationId) {
        setRecId(result.recommendation.recommendationId)
        setPopupPhase('polling')
      } else {
        setRecommendation(null)
        setPopupPhase('recommendation')
      }
    } catch {
      setPopupError('提交失败，请稍后再试')
      setPopupPhase('selfAssessment')
    }
  }

  const handleRestart = () => {
    resetPopup()
    setMode('focus')
    setRemaining(focusMinutes * 60)
  }

  const handleDone = () => {
    resetPopup()
    setRemaining(totalSeconds)
  }

  const handleSaveTask = () => {
    const next = draft.trim()
    if (next) {
      setTask(next)
      setTaskSource('edited')
    }
    setDraft(next || task)
    setEditing(false)
  }

  const handleCancelTask = () => {
    setDraft(task)
    setEditing(false)
  }

  return (
    <div className={styles.app}>
      <div className={styles.bgSky} aria-hidden="true" />

      <header className={styles.topbar}>
        <img className={styles.brandLogo} src="/brand/logo-full-on-light.png" alt="logo" />

        <div className={styles.taskInline}>
          {editing ? (
            <div className={styles.taskEdit}>
              <input
                className={styles.taskInput}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={40}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveTask()
                  if (e.key === 'Escape') handleCancelTask()
                }}
              />
              <button className={styles.iconBtn} onClick={handleSaveTask}>保存</button>
              <button className={`${styles.iconBtn} ${styles.ghost}`} onClick={handleCancelTask}>取消</button>
            </div>
          ) : (
            <div className={styles.taskView}>
              <span className={styles.taskLabel}>任务</span>
              <span className={styles.taskTitle}>{task}</span>
              <button className={`${styles.iconBtn} ${styles.ghost}`} onClick={() => setEditing(true)}>编辑</button>
            </div>
          )}
        </div>

        <label className={styles.subjectField}>
          <span className={styles.subjectLabel}>学科</span>
          <select
            className={styles.subjectSelect}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          >
            {Object.entries(subjectLabels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </label>

        <div className={styles.modeTabs}>
          <button
            className={`${styles.modeTab} ${mode === 'focus' ? styles.active : ''}`}
            onClick={() => setMode('focus')}
          >
            专注
          </button>
          <button
            className={`${styles.modeTab} ${mode === 'break' ? styles.active : ''}`}
            onClick={() => setMode('break')}
          >
            休息
          </button>
        </div>

        <DurationField label="专注" value={focusMinutes} min={0} max={180} onCommit={setFocusMinutes} />
        <DurationField label="休息" value={breakMinutes} min={0} max={60} onCommit={setBreakMinutes} />

        <span className={styles.timeBig}>{formatTime(remaining)}</span>

        <div className={styles.controls}>
          {!isRunning ? (
            <button
              className={`${styles.btn} ${styles.primary}`}
              disabled={totalSeconds <= 0 && remaining <= 0}
              onClick={() => {
                if (remaining === 0) {
                  setRemaining(totalSeconds)
                } else {
                  if (remaining === totalSeconds) setSessionStart(new Date().toISOString())
                  startTimer()
                }
              }}
            >
              {remaining === 0 ? '重新开始' : remaining === totalSeconds ? '开始' : '继续'}
            </button>
          ) : (
            <button className={`${styles.btn} ${styles.ghost}`} onClick={stopTimer}>
              暂停
            </button>
          )}
          <button
            className={`${styles.btn} ${styles.ghost}`}
            onClick={() => {
              stopTimer()
              setRemaining(totalSeconds)
            }}
          >
            重置
          </button>
        </div>
      </header>

      <main className={styles.centerStage}>
        <h1 className={styles.epochx}>EpochX</h1>
      </main>

      {showDone && (
        <div className={styles.completionPop}>
          {popupPhase === 'selfAssessment' && (
            <SelfAssessment
              task={task}
              error={popupError}
              planTaskStats={planTaskStats}
              onConfirm={handleConfirmSelfReport}
              onSkip={handleDone}
            />
          )}
          {popupPhase === 'submitting' && (
            <div className={styles.popLoading}>正在提交记录…</div>
          )}
          {popupPhase === 'polling' && (
            <div className={styles.popLoading}>正在生成学习建议…</div>
          )}
          {popupPhase === 'recommendation' && (
            <RecommendationPanel
              recommendation={recommendation}
              onOk={handleDone}
              onRestart={handleRestart}
            />
          )}
        </div>
      )}
    </div>
  )
}

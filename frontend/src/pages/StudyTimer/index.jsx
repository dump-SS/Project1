import { useState, useEffect, useRef, useCallback } from 'react'
import styles from './index.module.css'
import { subjectLabels } from '@/styles/theme'
import { createLearningRecord, getRecommendation } from '@/services/learningRecord'

const FOCUS_LABELS = { 1: '分心', 2: '一般', 3: '还好', 4: '专注', 5: '非常专注' }
const FATIGUE_LABELS = { 1: '精神', 2: '轻微', 3: '一般', 4: '疲劳', 5: '非常疲劳' }
const EMOTION_LABELS = { positive: '积极', neutral: '一般', negative: '消极' }
const DIFFICULTY_LABELS = { easy: '简单', moderate: '适中', hard: '困难' }

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

function SelfAssessment({ task, error, onConfirm, onSkip }) {
  const [focus, setFocus] = useState(null)
  const [fatigue, setFatigue] = useState(null)
  const [emotion, setEmotion] = useState(null)
  const [difficultyFeel, setDifficultyFeel] = useState(null)

  const complete = focus !== null && fatigue !== null && emotion !== null && difficultyFeel !== null

  const submit = () => {
    if (!complete) return
    onConfirm({ focus, fatigue, emotion, difficultyFeel })
  }

  return (
    <>
      <div className={styles.popHeader}>
        <span className={styles.popTitle}>任务完成</span>
        <span className={styles.popText}>「{task}」已完成</span>
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
  const status = recommendation?.generation?.status
  const items = recommendation?.items

  let body
  if (status === 'ready' && items && items.length > 0) {
    body = (
      <div className={styles.recList}>
        {items.map((item, index) => (
          <div key={index} className={styles.recItem}>
            <div className={styles.recTitle}>{item.title}</div>
            <div className={styles.recContent}>{item.content}</div>
          </div>
        ))}
      </div>
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
  const [task, setTask] = useState('复习函数章节')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(task)

  const [subject, setSubject] = useState('math')

  const [mode, setMode] = useState('focus')
  const [focusMinutes, setFocusMinutes] = useState(25)
  const [breakMinutes, setBreakMinutes] = useState(5)
  const [remaining, setRemaining] = useState(25 * 60)
  const [isRunning, setIsRunning] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [sessionStart, setSessionStart] = useState(null)

  const [popupPhase, setPopupPhase] = useState('selfAssessment')
  const [recId, setRecId] = useState(null)
  const [recommendation, setRecommendation] = useState(null)
  const [popupError, setPopupError] = useState(null)

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

  const handleConfirmSelfReport = async (selfReport) => {
    setPopupPhase('submitting')
    setPopupError(null)
    try {
      const result = await createLearningRecord({
        subject,
        startedAt: sessionStart || new Date(Date.now() - focusMinutes * 60000).toISOString(),
        durationMinutes: focusMinutes,
        behavior: { completion: 'completed' },
        selfReport,
      })

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
    if (next) setTask(next)
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

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import StudyEditor from '../StudyPlanEditor/StudyEditor.jsx'
import TaskList from '../StudyPlanEditor/TaskList.jsx'
import { usePlanFlow } from '@/hooks/usePlanFlow'
import { fetchRecommendationContent } from '@/services/recommendationContent'
import { subjectLabels } from '@/styles/theme'
import './index.css'
import './Guide.css'

export default function StudyGuide() {
  const navigate = useNavigate()
  const { state, validators, handlers } = usePlanFlow()
  const { taskValue, setTaskValue, minutes, setMinutes, plan, hasGenerated, submitError, offlineNote } = state
  const { MINUTES_VALIDATOR } = validators
  const { generate, handleEnter, handleTaskUpdated } = handlers

  // 学习科目(必填,新增)
  const [subject, setSubject] = useState('')

  // 交互阶段:'idle' | 'modal'(弹窗) | 'blackout'(黑场) | 'flooding'(水淹)
  const [stage, setStage] = useState('idle')

  // LLM 驱动的学习内容推荐(PRD 5.3 / 6.4)
  const [rec, setRec] = useState({
    eligible: false,
    recordCount: 0,
    recentWindowDays: 7,
    subject: null,
    topic: null,
    reason: '加载中…',
    fromLLM: false,
  })
  const [recLoading, setRecLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setRecLoading(true)
    fetchRecommendationContent()
      .then((data) => {
        if (cancelled) return
        setRec(data)
      })
      .finally(() => {
        if (!cancelled) setRecLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  // 点击 AUTO 自动填充:让 LLM 推荐的 subject + topic 落到表单
  const handleAutoFill = async () => {
    try {
      const { rec: generated, plan: newPlan } = await generate({ minMinutes: 60 })
      if (generated) setTaskValue(generated)
      // AUTO 时同步把推荐学科写入科目
      if (newPlan?.tasks?.[0]?.subject) setSubject(newPlan.tasks[0].subject)
    } catch (err) {
      console.warn('[AUTO 填充失败]', err)
    }
  }

  // 三项是否都填完:任务 + 时间(10-600) + 科目
  const allFilled = taskValue.trim() !== '' && MINUTES_VALIDATOR(minutes) && subject !== ''

  // 点击「进入」按钮:先生成计划,成功后显示弹窗
  const handleEnterClick = async () => {
    if (!allFilled) return
    const ok = await handleEnter()
    // handleEnter 返回 true 表示已生成可直接跳转;false 表示刚生成
    // 两种情况都进入弹窗阶段
    if (ok || hasGenerated || plan) {
      setStage('modal')
    }
  }

  // 弹窗「确认计划无误」→ 进入黑场
  const handleConfirmPlan = () => {
    setStage('blackout')
  }

  // 黑场窄条「进入计时 ENTER」:click 或 Enter 触发水淹
  const handleEnterTimer = () => {
    setStage('flooding')
  }

  // 水淹动画结束后跳转
  useEffect(() => {
    if (stage !== 'flooding') return
    const timer = setTimeout(() => {
      navigate('/study-timer', {
        state: {
          availableMinutes: MINUTES_VALIDATOR(minutes) ? Number(minutes) : 60,
          task: taskValue || null,
          subject: subject || null,
          planId: plan?.planId || null,
        },
      })
    }, 1400) // 与水淹动画时长一致
    return () => clearTimeout(timer)
  }, [stage, navigate, minutes, taskValue, subject, plan, MINUTES_VALIDATOR])

  // 黑场阶段监听 Enter 键
  useEffect(() => {
    if (stage !== 'blackout') return
    const onKey = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleEnterTimer()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stage])

  const subjectName = rec.subject ? (subjectLabels[rec.subject] ?? rec.subject) : ''

  return (
    <>
      <div className="page-background" aria-hidden="true">
        {/* 云朵装饰:散布页面边缘,不同速度缓慢飘动 */}
        <svg className="cloud-deco cloud-deco-1" viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
          <path d="M 30 70 Q 20 55 35 50 Q 40 30 60 32 Q 75 15 95 28 Q 115 20 125 35 Q 145 32 150 50 Q 165 55 160 70 Z" fill="currentColor" />
        </svg>
        <svg className="cloud-deco cloud-deco-2" viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
          <path d="M 30 70 Q 20 55 35 50 Q 40 30 60 32 Q 75 15 95 28 Q 115 20 125 35 Q 145 32 150 50 Q 165 55 160 70 Z" fill="currentColor" />
        </svg>
        <svg className="cloud-deco cloud-deco-3" viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
          <path d="M 30 70 Q 20 55 35 50 Q 40 30 60 32 Q 75 15 95 28 Q 115 20 125 35 Q 145 32 150 50 Q 165 55 160 70 Z" fill="currentColor" />
        </svg>
        <svg className="cloud-deco cloud-deco-4" viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
          <path d="M 30 70 Q 20 55 35 50 Q 40 30 60 32 Q 75 15 95 28 Q 115 20 125 35 Q 145 32 150 50 Q 165 55 160 70 Z" fill="currentColor" />
        </svg>

        {/* 海浪装饰:页面底部,双层波浪,右端延伸至屏幕右侧外 */}
        <svg className="wave-deco wave-deco-back" viewBox="0 0 1600 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M0,60 C200,90 400,30 600,60 C800,90 1000,30 1200,60 C1400,90 1520,40 1600,70 L1600,120 L0,120 Z" fill="currentColor" />
        </svg>
        <svg className="wave-deco wave-deco-front" viewBox="0 0 1600 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M0,80 C200,50 400,100 600,70 C800,40 1000,90 1200,70 C1400,50 1520,95 1600,75 L1600,120 L0,120 Z" fill="currentColor" />
        </svg>

        {/* 水淹过渡层:进入计时时海浪抬升淹没页面 */}
        {stage === 'flooding' && (
          <div className="flood-layer" aria-hidden="true">
            <svg className="flood-wave flood-wave-back" viewBox="0 0 1600 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M0,60 C200,90 400,30 600,60 C800,90 1000,30 1200,60 C1400,90 1520,40 1600,70 L1600,120 L0,120 Z" fill="currentColor" />
            </svg>
            <svg className="flood-wave flood-wave-front" viewBox="0 0 1600 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M0,80 C200,50 400,100 600,70 C800,40 1000,90 1200,70 C1400,50 1520,95 1600,75 L1600,120 L0,120 Z" fill="currentColor" />
            </svg>
            {/* 浪花飞溅 */}
            <div className="flood-foam flood-foam-1" />
            <div className="flood-foam flood-foam-2" />
            <div className="flood-foam flood-foam-3" />
            <div className="flood-foam flood-foam-4" />
            <div className="flood-foam flood-foam-5" />
            <div className="flood-foam flood-foam-6" />
          </div>
        )}
      </div>

      <main className="app">
        <h1 className="page-title">
          导学计划
          <span className="en">Study Guide</span>
        </h1>

        {/* LLM 学习内容推荐块(PRD 5.3 / 6.4) */}
        <div className="recommend" aria-hidden="true">
          <p className="recommend-line">
            学习内容推荐<span className="en">Recommendation{rec.fromLLM ? ' · AI' : ''}</span>
          </p>
          <p className="recommend-line">
            {recLoading
              ? '正在为你推荐下一个学习内容…'
              : !rec.eligible
                ? rec.reason
                : subjectName
                  ? `${subjectName} · ${rec.topic}`
                  : rec.reason}
          </p>
          {rec.eligible && rec.reason && (
            <p className="recommend-reason">{rec.reason}</p>
          )}
        </div>

        <button
          type="button"
          className="auto-fill"
          onClick={handleAutoFill}
          disabled={recLoading}
        >
          AUTO自动填充
        </button>

        <StudyEditor
          cnLabel="学习任务设置"
          enLabel="Study Task Setting"
          placeholder="e.g. 复习函数章节"
          value={taskValue}
          onChange={(event) => setTaskValue(event.target.value)}
        />

        <StudyEditor
          cnLabel="学习时间设置"
          enLabel="Study Time Setting"
          placeholder="可用分钟,10-600"
          inputType="number"
          validate={MINUTES_VALIDATOR}
          value={minutes}
          onChange={(event) => setMinutes(event.target.value)}
        />

        {/* 学习科目选择(新增必填) */}
        <div className="subject-picker">
          <p className="subject-picker-label">
            学习科目
            <span className="en">Subject</span>
          </p>
          <div className="subject-options" role="radiogroup" aria-label="学习科目">
            {Object.entries(subjectLabels).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={subject === key}
                className={`subject-chip ${subject === key ? 'subject-chip-active' : ''}`}
                onClick={() => setSubject(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {plan && stage === 'idle' && <TaskList plan={plan} onTaskUpdated={handleTaskUpdated} />}

        {plan?.weaknessHints && plan.weaknessHints.length > 0 && (
          <div className="weakness-hints" role="note">
            <p className="weakness-title">建议先补</p>
            <ul>
              {plan.weaknessHints.map((h) => (
                <li key={h.pointId}>
                  {h.pointName}
                  <span className="weakness-mastery">当前掌握 {Math.round(h.mastery * 100)}%</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {submitError && <p className="submit-error">{submitError}</p>}
        {offlineNote && <p className="submit-error">{offlineNote}</p>}

        {/* 进入按钮:三项填完才可点 */}
        <button
          type="button"
          className="enter-button"
          onClick={handleEnterClick}
          disabled={!allFilled}
          aria-disabled={!allFilled}
        >
          {allFilled ? '进入' : '请先填写完整'}
          <span className="enter-en">{allFilled ? 'ENTER' : 'FILL ALL FIELDS'}</span>
        </button>
      </main>

      {/* 计划确认弹窗(三项填完点「进入」后显示) */}
      {stage === 'modal' && plan && (
        <>
          <div className="modal-mask" onClick={() => setStage('idle')} aria-hidden="true" />
          <div className="plan-modal" role="dialog" aria-modal="true" aria-labelledby="plan-modal-title">
            <h2 id="plan-modal-title" className="plan-modal-title">
              计划已生成
              <span className="en">Plan Ready</span>
            </h2>
            <p className="plan-modal-subtitle">请确认以下学习计划</p>

            <div className="plan-modal-body">
              <div className="plan-modal-row">
                <span className="plan-modal-label">学习科目</span>
                <span className="plan-modal-value">{subjectLabels[subject] ?? subject}</span>
              </div>
              <div className="plan-modal-row">
                <span className="plan-modal-label">学习任务</span>
                <span className="plan-modal-value">{taskValue}</span>
              </div>
              <div className="plan-modal-row">
                <span className="plan-modal-label">可用时长</span>
                <span className="plan-modal-value">{minutes} 分钟</span>
              </div>
              {plan.tasks?.length > 0 && (
                <div className="plan-modal-tasks">
                  <p className="plan-modal-label">拆解任务</p>
                  <ul>
                    {plan.tasks.slice(0, 3).map((t) => (
                      <li key={t.taskId}>{subjectLabels[t.subject] ?? t.subject} · {t.topic}</li>
                    ))}
                    {plan.tasks.length > 3 && <li className="plan-modal-more">…共 {plan.tasks.length} 项</li>}
                  </ul>
                </div>
              )}
            </div>

            <div className="plan-modal-actions">
              <button
                type="button"
                className="plan-modal-btn plan-modal-btn-ghost"
                onClick={() => setStage('idle')}
              >
                返回修改
              </button>
              <button
                type="button"
                className="plan-modal-btn plan-modal-btn-primary"
                onClick={handleConfirmPlan}
                autoFocus
              >
                确认无误
              </button>
            </div>
          </div>
        </>
      )}

      {/* 黑场 + 横向液态玻璃窄条「进入计时 ENTER」 */}
      {stage === 'blackout' && (
        <div className="blackout-layer" role="presentation">
          <button
            type="button"
            className="blackout-strip"
            onClick={handleEnterTimer}
            aria-label="进入计时"
          >
            <span className="blackout-strip-text">进入计时</span>
            <span className="blackout-strip-en">ENTER</span>
          </button>
        </div>
      )}
    </>
  )
}

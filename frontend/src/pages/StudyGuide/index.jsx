import { useEffect, useState } from 'react'
import StudyEditor from '../StudyPlanEditor/StudyEditor.jsx'
import EnterButton from '../StudyPlanEditor/EnterButton.jsx'
import TaskList from '../StudyPlanEditor/TaskList.jsx'
import { usePlanFlow } from '@/hooks/usePlanFlow'
import { fetchRecommendationContent } from '@/services/recommendationContent'
import { subjectLabels } from '@/styles/theme'
import './index.css'
import './Guide.css'

export default function StudyGuide() {
  const { state, validators, handlers } = usePlanFlow()
  const { taskValue, setTaskValue, minutes, setMinutes, plan, hasGenerated, submitError, offlineNote } = state
  const { MINUTES_VALIDATOR } = validators
  const { generate, handleEnter, handleTaskUpdated } = handlers

  // LLM 驱动的学习内容推荐（PRD 5.3 / 6.4）
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

  // 点击 AUTO 自动填充：直接调 generate() 让 LLM 推荐的 subject 落到 plan
  // 然后把"学科 · 主题"回填到学习任务输入框
  const handleAutoFill = async () => {
    try {
      const { rec: generated } = await generate({ minMinutes: 60 })
      if (generated) setTaskValue(generated)
    } catch (err) {
      // usePlanFlow 内部已设置 submitError；这里只兜底
      console.warn('[AUTO 填充失败]', err)
    }
  }

  const subjectName = rec.subject ? (subjectLabels[rec.subject] ?? rec.subject) : ''

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          导学计划
          <span className="en">Study Guide</span>
        </h1>

        {/* LLM 学习内容推荐块（PRD 5.3 / 6.4） */}
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
          placeholder="可用分钟，10-600"
          inputType="number"
          validate={MINUTES_VALIDATOR}
          value={minutes}
          onChange={(event) => setMinutes(event.target.value)}
        />

        {plan && <TaskList plan={plan} onTaskUpdated={handleTaskUpdated} />}

        {submitError && <p className="submit-error">{submitError}</p>}
        {offlineNote && <p className="submit-error">{offlineNote}</p>}

        <EnterButton
          to="/study-timer"
          onBeforeNavigate={handleEnter}
          state={{
            // 番茄钟页接 state 来同步可用分钟 + 任务（PRD 5.1：计划与执行端参数一致）
            availableMinutes: MINUTES_VALIDATOR(minutes) ? Number(minutes) : 60,
            task: taskValue || rec.subject && rec.topic
              ? `${subjectLabels[rec.subject] ?? rec.subject} · ${rec.topic}`
              : null,
            planId: plan?.planId || null,
          }}
        />
      </main>
    </>
  )
}

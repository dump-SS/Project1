import { useState, useEffect } from 'react'
import StudyEditor from './StudyEditor.jsx'
import EnterButton from './EnterButton.jsx'
import TaskList from './TaskList.jsx'
import { createPlan, getPlanByDate, localDateString } from '../../services/plans'
import { isNetworkError } from '../../services/http'
import './index.css'
import './App.css'
import './TaskList.css'

/**
 * 可用学习分钟校验：整数，10-600。
 * 对齐 openapi.yaml PlanCreate.availableMinutes（minimum 10 / maximum 600）。
 */
const MINUTES_VALIDATOR = (value) => {
  if (value === '') return false
  const n = Number(value)
  return Number.isInteger(n) && n >= 10 && n <= 600
}

export default function StudyPlanEditor() {
  // 「学习任务设置」受控值（与 StudyGuide 保持一致，未来可加 AUTO 填充等程序化写入）
  const [taskValue, setTaskValue] = useState('')
  // 可用学习分钟（受控，用于 POST /plans）
  const [minutes, setMinutes] = useState('')
  // 当前已生成的计划（用于渲染 TaskList 与标记完成）
  const [plan, setPlan] = useState(null)
  // 是否已经生成过计划（用于决定「进入」点击是「生成」还是「跳转」）
  const [hasGenerated, setHasGenerated] = useState(false)
  // 当日是否已有计划（用于在点进入时自动 regenerate，避免 409）
  // 挂载时拉一次；用户改分钟后点进入会带上 regenerate=true 覆盖
  const [hasExistingPlan, setHasExistingPlan] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [offlineNote, setOfflineNote] = useState('')

  // 挂载时查当日是否已有计划（用于决定 createPlan 时是否传 regenerate）
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const existing = await getPlanByDate(localDateString())
      if (!cancelled && existing) {
        setHasExistingPlan(true)
        // 把已有计划的分钟/任务回填进输入框，让用户感知「这是覆盖」
        if (existing.availableMinutes != null) setMinutes(String(existing.availableMinutes))
        if (existing.tasks?.[0]?.topic && !taskValue) {
          setTaskValue(existing.tasks[0].topic)
        }
      }
    })()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 点「进入」：
   *  - 第一次点击：同步生成计划（POST /plans），成功后停留在页面展示任务列表，等待用户标记完成
   *  - 后续点击：放行 EnterButton 跳转 /study-timer
   */
  const handleEnter = async () => {
    if (hasGenerated) return true
    setSubmitError('')
    setOfflineNote('')
    if (!MINUTES_VALIDATOR(minutes)) {
      setSubmitError('请先填写 10-600 的可用学习分钟数')
      return false
    }
    try {
      const { plan: created, fromCache } = await createPlan({
        planDate: localDateString(),
        availableMinutes: Number(minutes),
        // 当日已有计划时自动覆盖（用户既然改了分钟就是要重生成）
        regenerate: hasExistingPlan || undefined,
      })
      if (fromCache) {
        setOfflineNote('离线取用上次成功计划')
      }
      setPlan(created)
      setHasGenerated(true)
      setHasExistingPlan(true)  // 生成后一定存在
      // 生成成功后留在本页面，让用户能完成/调整任务；下一次点「进入」才跳转
      return false
    } catch (err) {
      setSubmitError(isNetworkError(err) ? '服务暂不可用，请稍后再试' : (err?.message ?? '计划生成失败，请稍后再试'))
      return false
    }
  }

  /** 任务 PATCH 成功后，更新本地 plan 的对应 task 字段 */
  const handleTaskUpdated = (updated) => {
    setPlan((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        tasks: prev.tasks.map((t) => (t.taskId === updated.taskId ? { ...t, ...updated } : t)),
      }
    })
  }

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          学习计划编辑
          <br />
          <span className="en">Study Plan Editor</span>
        </h1>

        <StudyEditor
          cnLabel="学习时间设置"
          enLabel="Study Time Setting"
          placeholder="可用分钟，10-600"
          inputType="number"
          validate={MINUTES_VALIDATOR}
          value={minutes}
          onChange={(event) => setMinutes(event.target.value)}
        />

        <StudyEditor
          cnLabel="学习任务设置"
          enLabel="Study Task Setting"
          placeholder="e.g. 复习函数章节"
          value={taskValue}
          onChange={(event) => setTaskValue(event.target.value)}
        />

        {plan && <TaskList plan={plan} onTaskUpdated={handleTaskUpdated} />}

        {submitError && <p className="submit-error">{submitError}</p>}
        {offlineNote && <p className="submit-error">{offlineNote}</p>}

        <EnterButton
          to="/study-timer"
          onBeforeNavigate={handleEnter}
          state={{
            // 番茄钟页接 state 来同步可用分钟 + 任务（PRD 5.1：计划与执行端参数一致）
            availableMinutes: MINUTES_VALIDATOR(minutes) ? Number(minutes) : null,
            task: taskValue || null,
            planId: plan?.planId || null,
          }}
        />
      </main>
    </>
  )
}
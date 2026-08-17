import { useState } from 'react'
import StudyEditor from './StudyEditor.jsx'
import EnterButton from './EnterButton.jsx'
import { createPlan, localDateString } from '../../services/plans'
import './index.css'
import './App.css'

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
  // 可用学习分钟（受控，用于 POST /plans）
  const [minutes, setMinutes] = useState('')
  const [submitError, setSubmitError] = useState('')

  /** 点「进入」：先同步生成计划（POST /plans），成功后跳专注计时页 */
  const handleEnter = async () => {
    setSubmitError('')
    if (!MINUTES_VALIDATOR(minutes)) {
      setSubmitError('请先填写 10-600 的可用学习分钟数')
      return false
    }
    try {
      await createPlan({
        planDate: localDateString(),
        availableMinutes: Number(minutes),
      })
      return true
    } catch (err) {
      setSubmitError(err?.message ?? '计划生成失败，请稍后再试')
      return false
    }
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
        />

        {submitError && <p className="submit-error">{submitError}</p>}

        <EnterButton to="/study-timer" onBeforeNavigate={handleEnter} />
      </main>
    </>
  )
}
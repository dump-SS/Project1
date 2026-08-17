import { useState } from 'react'
import StudyEditor from '../StudyPlanEditor/StudyEditor.jsx'
import EnterButton from '../StudyPlanEditor/EnterButton.jsx'
import { createPlan, localDateString } from '../../services/plans'
import { isNetworkError } from '../../services/http'
import { subjectLabels } from '@/styles/theme'
import './index.css'
import './Guide.css'

/**
 * 可用学习分钟校验：整数，10-600。
 * 对齐 openapi.yaml PlanCreate.availableMinutes（minimum 10 / maximum 600）。
 */
const MINUTES_VALIDATOR = (value) => {
  if (value === '') return false
  const n = Number(value)
  return Number.isInteger(n) && n >= 10 && n <= 600
}

export default function StudyGuide() {
  // 「学习任务设置」的值由页面管理，便于「AUTO自动填充」程序化写入
  const [taskValue, setTaskValue] = useState('')
  // 可用学习分钟（受控，用于 POST /plans）
  const [minutes, setMinutes] = useState('')
  // 推荐学科：来自本次生成的计划任务（规则引擎，非 LLM）
  const [recommendation, setRecommendation] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [offlineNote, setOfflineNote] = useState('')

  const handleAutoFill = () => {
    if (recommendation) setTaskValue(recommendation)
  }

  /** 点「进入」：先同步生成计划（POST /plans），成功后跳专注计时页 */
  const handleEnter = async () => {
    setSubmitError('')
    setOfflineNote('')
    if (!MINUTES_VALIDATOR(minutes)) {
      setSubmitError('请先填写 10-600 的可用学习分钟数')
      return false
    }
    try {
      const { plan, fromCache } = await createPlan({
        planDate: localDateString(),
        availableMinutes: Number(minutes),
      })
      // 规则引擎：从计划任务里挑一条当推荐，替代原硬编码常量 DEFAULT_SUBJECT
      // 离线回退时 plan 为缓存计划，同样含有 tasks，AUTO 填充可继续工作
      const first = plan.tasks?.[0]
      if (first) {
        const label = subjectLabels[first.subject] ?? first.subject
        setRecommendation(`${label} · ${first.topic}`)
      }
      // 网络失败回退到缓存时 createPlan 会返回缓存计划并标记 fromCache
      if (fromCache) {
        setOfflineNote('离线取用上次成功计划')
      }
      return true
    } catch (err) {
      setSubmitError(isNetworkError(err) ? '服务暂不可用，请稍后再试' : (err?.message ?? '计划生成失败，请稍后再试'))
      return false
    }
  }

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          导学计划
          <span className="en">Study Guide</span>
        </h1>

        <div className="recommend" aria-hidden="true">
          <p className="recommend-line">
            我所推荐的<span className="en">Recommendation…</span>
          </p>
          <p className="recommend-line">
            {recommendation || '填写学习分钟后点击进入，将按本次计划自动推荐'}
          </p>
        </div>

        <button type="button" className="auto-fill" onClick={handleAutoFill}>
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

        {submitError && <p className="submit-error">{submitError}</p>}
        {offlineNote && <p className="submit-error">{offlineNote}</p>}

        <EnterButton to="/study-timer" onBeforeNavigate={handleEnter} />
      </main>
    </>
  )
}
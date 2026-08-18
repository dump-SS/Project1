import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

/**
 * 「进入」键：白色背景，含「进入」与「ENTER」字样。
 * 点击后跳去 to 指定的路由——语义是「按这份计划开始执行学习任务」。
 * StudyGuide 与 StudyPlanEditor 都传 to="/study-timer"（专注计时页）。
 *
 * @param {Function} [onBeforeNavigate] 可选异步钩子：返回 Promise<boolean>。
 *   await 后才跳转；返回值严格为 false 则不跳转（用于「生成计划校验/失败时不进入」）。
 *   等待期间防重复点击（busy）。
 * @param {object} [state] 透传给目标路由的 location.state。
 *   StudyTimer 用它读取「可用分钟 / 任务 / planId」，避免番茄钟页用错默认值。
 */
export default function EnterButton({ to = '/study-timer', onBeforeNavigate, state }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  const handleClick = async (e) => {
    e.preventDefault()
    if (busy) return

    let proceed = true
    if (onBeforeNavigate) {
      setBusy(true)
      try {
        proceed = await onBeforeNavigate()
      } finally {
        setBusy(false)
      }
    }
    if (proceed !== false) {
      navigate(to, state ? { state } : undefined)
    }
  }

  return (
    <a
      className="enter-button"
      href={to}
      aria-label="进入"
      aria-busy={busy}
      onClick={handleClick}
    >
      {busy && <span className="spinner spinner--sm" aria-hidden="true" />}
      进入
      <span className="enter-en">ENTER</span>
    </a>
  )
}

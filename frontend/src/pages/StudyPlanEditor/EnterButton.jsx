/**
 * 「进入」键：白色背景，含「进入」与「ENTER」字样。
 * 点击后跳去 to 指定的路由——语义是「按这份计划开始执行学习任务」，
 * 目前 StudyGuide 与 StudyPlanEditor 都传 to="/study-timer"（专注计时页）。
 */
import { useNavigate } from 'react-router-dom'

export default function EnterButton({ to = '/study-timer' }) {
  const navigate = useNavigate()

  return (
    <a
      className="enter-button"
      href={to}
      aria-label="进入"
      onClick={(e) => {
        e.preventDefault()
        navigate(to)
      }}
    >
      进入
      <span className="enter-en">ENTER</span>
    </a>
  )
}

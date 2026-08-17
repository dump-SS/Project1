import { useState } from 'react'
import { updatePlanTask } from '../../services/plans'
import { subjectLabels } from '@/styles/theme'
import './TaskList.css'

/**
 * 状态标签中文名。对应 openapi.yaml components.schemas.TaskStatus（pending/completed/partial/abandoned）。
 * PRD 6.1：状态由后端规则层判定，前端只展示。
 */
const STATUS_LABELS = {
  pending: '待开始',
  completed: '已完成',
  partial: '部分完成',
  abandoned: '已放弃',
}

/**
 * 计划任务列表。
 * 把 plan.tasks[] 渲染成可读列表：优先级 P1/P2/... + 学科中文 + 主题 + 预计时长 + 完成按钮。
 * 任务完成走 PATCH /plans/{planId}/tasks/{taskId}（服务层 updatePlanTask），
 * 后端缺该 endpoint 时会收到 404，组件会显示行内错误并不影响其他任务。
 *
 * @param {Object}   plan              由 createPlan() 返回的 Plan
 * @param {Function} [onTaskUpdated]   可选。任务更新成功后回调，签名 (updatedTask: PlanTask) => void
 */
export default function TaskList({ plan, onTaskUpdated }) {
  // 当前正在提交的任务 id，用于「完成」按钮的 busy 态
  const [busyTaskId, setBusyTaskId] = useState(null)
  // 行内错误（按 taskId 存，5s 自动清）
  const [rowErrors, setRowErrors] = useState({})

  if (!plan || !Array.isArray(plan.tasks) || plan.tasks.length === 0) return null

  const handleComplete = async (task) => {
    if (task.status === 'completed') return
    setBusyTaskId(task.taskId)
    setRowErrors((prev) => {
      const next = { ...prev }
      delete next[task.taskId]
      return next
    })
    try {
      const updated = await updatePlanTask(plan.planId, task.taskId, { status: 'completed' })
      if (onTaskUpdated) onTaskUpdated(updated)
    } catch (err) {
      // 后端 PATCH 缺失时会拿到 404；其他错误按 http 错误统一处理
      const msg = err?.status === 404
        ? '后端尚未实现 PATCH 接口'
        : (err?.message ?? '更新失败，请稍后再试')
      setRowErrors((prev) => ({ ...prev, [task.taskId]: msg }))
      // 5s 后自动清掉错误
      setTimeout(() => {
        setRowErrors((prev) => {
          const next = { ...prev }
          delete next[task.taskId]
          return next
        })
      }, 5000)
    } finally {
      setBusyTaskId(null)
    }
  }

  return (
    <ul className="task-list" aria-label="本次学习计划任务">
      {plan.tasks.map((task) => {
        const isDone = task.status === 'completed'
        const isBusy = busyTaskId === task.taskId
        const subjectLabel = subjectLabels[task.subject] ?? task.subject
        const statusLabel = STATUS_LABELS[task.status] ?? task.status
        const errMsg = rowErrors[task.taskId]
        return (
          <li
            key={task.taskId}
            className={`task-item${isDone ? ' is-done' : ''}`}
            data-status={task.status}
          >
            <span className="task-priority" aria-label={`优先级 ${task.priority}`}>
              P{task.priority}
            </span>
            <div className="task-body">
              <p className="task-subject">
                {subjectLabel}
                <span className="task-subject-en">{task.subject}</span>
              </p>
              <p className="task-topic">{task.topic}</p>
              <p className="task-meta">
                <span className="task-time" title="预计时长">
                  <span className="task-time-icon" aria-hidden="true">⏱</span>
                  {task.estimatedMinutes} min
                </span>
                <span className={`task-status task-status-${task.status}`}>
                  {statusLabel}
                </span>
              </p>
              {errMsg && <p className="task-error" role="alert">{errMsg}</p>}
            </div>
            <div className="task-action">
              {isDone ? (
                <span className="task-done-mark" aria-label="已完成">✓ 已完成</span>
              ) : (
                <button
                  type="button"
                  className="task-complete-btn"
                  onClick={() => handleComplete(task)}
                  disabled={isBusy}
                  aria-busy={isBusy}
                >
                  {isBusy ? '提交中…' : '完成'}
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

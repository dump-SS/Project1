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

const MIN_MINUTES = 5
const MAX_MINUTES = 600

/**
 * 计划任务列表 —— D4「任务卡卡内可直接操作」。
 *
 * 卡内三种操作，全部直达 `PATCH /plans/{planId}/tasks/{taskId}`：
 * - **勾选完成** → `{ status: 'completed' }`
 * - **改时间**（点时长数字变输入框）→ `{ estimatedMinutes }`
 * - **删除** → `{ removed: true }`（**软删除**）
 *
 * 为什么删除是软删除而不是真删：`removed=true` 保留了「用户不认可这条算法建议」这个
 * 反馈信号（后端会同时标记 `userAdjusted`），真删掉就把调权依据丢了。
 * 界面上它照样消失——用户看到的语义就是"删掉了"。
 *
 * 本地 `overrides` / `removedIds` 让组件在父级不回调时也能正确反映改动，
 * 不必依赖调用方实现 `onTaskUpdated`。
 *
 * @param {Object}   plan              由 createPlan() 返回的 Plan
 * @param {Function} [onTaskUpdated]   可选。任务更新成功后回调，签名 (updatedTask: PlanTask) => void
 */
export default function TaskList({ plan, onTaskUpdated }) {
  // 当前正在提交的任务 id，用于按钮 busy 态
  const [busyTaskId, setBusyTaskId] = useState(null)
  // 行内错误（按 taskId 存，5s 自动清）
  const [rowErrors, setRowErrors] = useState({})
  // 本地覆盖：用户刚改过的字段，优先于 props（父级不回调也不影响显示）
  const [overrides, setOverrides] = useState({})
  // 本地移除：软删除后立即从列表消失
  const [removedIds, setRemovedIds] = useState([])
  // 正在编辑时长的任务 id 与草稿
  const [editingId, setEditingId] = useState(null)
  const [draftMinutes, setDraftMinutes] = useState('')

  if (!plan || !Array.isArray(plan.tasks) || plan.tasks.length === 0) return null

  const rows = plan.tasks
    .filter((t) => !removedIds.includes(t.taskId))
    .map((t) => ({ ...t, ...overrides[t.taskId] }))

  if (rows.length === 0) {
    return (
      <p className="task-empty" role="status">
        这次的任务都被移除了。可以重新生成一份计划，或直接进入计时自由学习。
      </p>
    )
  }

  const showError = (taskId, msg) => {
    setRowErrors((prev) => ({ ...prev, [taskId]: msg }))
    // 5s 后自动清掉错误
    setTimeout(() => {
      setRowErrors((prev) => {
        const next = { ...prev }
        delete next[taskId]
        return next
      })
    }, 5000)
  }

  const patchTask = async (task, patch, onOk) => {
    setBusyTaskId(task.taskId)
    setRowErrors((prev) => {
      const next = { ...prev }
      delete next[task.taskId]
      return next
    })
    try {
      const updated = await updatePlanTask(plan.planId, task.taskId, patch)
      onOk(updated)
      if (onTaskUpdated) onTaskUpdated(updated)
      return true
    } catch (err) {
      const msg = err?.status === 404
        ? '后端尚未实现 PATCH 接口'
        : (err?.message ?? '更新失败，请稍后再试')
      showError(task.taskId, msg)
      return false
    } finally {
      setBusyTaskId(null)
    }
  }

  const handleComplete = (task) => {
    if (task.status === 'completed') return
    patchTask(task, { status: 'completed' }, () => {
      setOverrides((prev) => ({ ...prev, [task.taskId]: { ...prev[task.taskId], status: 'completed' } }))
    })
  }

  const startEditMinutes = (task) => {
    setEditingId(task.taskId)
    setDraftMinutes(String(task.estimatedMinutes ?? 30))
  }

  const commitMinutes = async (task) => {
    const parsed = parseInt(draftMinutes, 10)
    const minutes = Number.isNaN(parsed)
      ? (task.estimatedMinutes ?? 30)
      : Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, parsed))
    setEditingId(null)

    if (minutes === task.estimatedMinutes) return // 没改就别发请求
    await patchTask(task, { estimatedMinutes: minutes }, () => {
      setOverrides((prev) => ({ ...prev, [task.taskId]: { ...prev[task.taskId], estimatedMinutes: minutes } }))
    })
  }

  const handleRemove = async (task) => {
    // 失败时 onOk 不会执行，任务留在列表里——不能让它"看起来删掉了"
    await patchTask(task, { removed: true }, () => {
      setRemovedIds((prev) => [...prev, task.taskId])
    })
  }

  return (
    <ul className="task-list" aria-label="本次学习计划任务">
      {rows.map((task) => {
        const isDone = task.status === 'completed'
        const isBusy = busyTaskId === task.taskId
        const subjectLabel = subjectLabels[task.subject] ?? task.subject
        const statusLabel = STATUS_LABELS[task.status] ?? task.status
        const errMsg = rowErrors[task.taskId]
        const isEditingMinutes = editingId === task.taskId
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
                {isEditingMinutes ? (
                  <span className="task-time-editing">
                    <span className="task-time-icon" aria-hidden="true">⏱</span>
                    <input
                      className="task-time-input"
                      type="number"
                      min={MIN_MINUTES}
                      max={MAX_MINUTES}
                      value={draftMinutes}
                      autoFocus
                      onChange={(e) => setDraftMinutes(e.target.value)}
                      onBlur={() => commitMinutes(task)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') e.currentTarget.blur()
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                    />
                    <span className="task-time-unit">min</span>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="task-time task-time-btn"
                    title="点击修改预计时长"
                    onClick={() => startEditMinutes(task)}
                    disabled={isBusy}
                  >
                    <span className="task-time-icon" aria-hidden="true">⏱</span>
                    {task.estimatedMinutes} min
                  </button>
                )}
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
              <button
                type="button"
                className="task-remove-btn"
                title="从今天的计划里移除"
                onClick={() => handleRemove(task)}
                disabled={isBusy}
              >
                移除
              </button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

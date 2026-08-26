import { useEffect, useMemo, useState } from 'react'
import {
  archiveGoal,
  createGoal,
  fetchGoals,
  updateGoal,
} from '../../services/goals'
import { isNetworkError } from '../../services/http'
import { fetchKnowledgePoints } from '../../services/knowledgeV2'
import { subjectLabels } from '@/styles/theme'
import { dayjs } from '@/utils/aggregate'
import './index.css'
import './App.css'

/**
 * 目标类型 / 学科的可选项。复用 openapi.yaml 的枚举：
 * - type: short_term / long_term
 * - subject: Subject 全 10 项（YW..other）
 */
const GOAL_TYPES = [
  { value: 'short_term', cn: '短期', en: 'Short Term' },
  { value: 'long_term', cn: '长期', en: 'Long Term' },
]

const SUBJECTS = Object.keys(subjectLabels)

const TYPE_LABEL = GOAL_TYPES.reduce((acc, t) => {
  acc[t.value] = t.cn
  return acc
}, {})

/** 单条 title 的长度校验：openapi.yaml GoalCreate.title ≤ 50 */
const TITLE_MAX = 50
/** description ≤ 200 */
const DESC_MAX = 200

const emptyForm = () => ({
  type: 'short_term',
  subject: SUBJECTS[0],
  title: '',
  description: '',
  targetDate: '',
  pointIds: [],
})

/**
 * 把后端返回的 Goal 拍平成本地编辑表单。已归档目标不在表单范围。
 */
function goalToForm(goal) {
  return {
    type: goal.type,
    subject: goal.subject,
    title: goal.title,
    description: goal.description ?? '',
    targetDate: goal.targetDate ?? '',
    pointIds: goal.pointIds ?? [],
  }
}

export default function Goals() {
  const [goals, setGoals] = useState({ active: [], finished: [] })
  const [form, setForm] = useState(emptyForm())
  /** 当前正在编辑的 active goal.id；为 null 时是「新建」态 */
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  /** 知识点候选（学科联动，T3） */
  const [points, setPoints] = useState([])

  useEffect(() => {
    let cancelled = false
    setPoints([])
    if (form.subject) {
      fetchKnowledgePoints(form.subject)
        .then((items) => {
          if (!cancelled) setPoints(items)
        })
        .catch(() => {
          if (!cancelled) setPoints([])
        })
    }
    return () => {
      cancelled = true
    }
  }, [form.subject])

  /** 拉取一次，把 active/finished 装进本地 state */
  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchGoals()
      setGoals(data)
    } catch (err) {
      setError(isNetworkError(err) ? '后端暂不可用，请稍后再试' : (err?.message ?? '加载失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const editingGoal = useMemo(
    () => goals.active.find((g) => g.goalId === editingId) ?? null,
    [goals.active, editingId],
  )

  const handleChange = (field) => (event) => {
    const value = event?.target?.value ?? event
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleNew = () => {
    setEditingId(null)
    setForm(emptyForm())
    setError('')
    setInfo('')
  }

  const handleEdit = (goal) => {
    setEditingId(goal.goalId)
    setForm(goalToForm(goal))
    setError('')
    setInfo('')
  }

  /** 校验 title：必填 + ≤ TITLE_MAX。description ≤ DESC_MAX。targetDate 不晚于一年后只是温和提示，不阻塞 */
  const validate = () => {
    if (!form.title.trim()) return '请填写目标标题'
    if (form.title.length > TITLE_MAX) return `标题需 ≤ ${TITLE_MAX} 字`
    if ((form.description?.length ?? 0) > DESC_MAX) return `描述需 ≤ ${DESC_MAX} 字`
    return ''
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setInfo('')
    const msg = validate()
    if (msg) {
      setError(msg)
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        type: form.type,
        subject: form.subject,
        title: form.title.trim(),
        description: form.description?.trim() || undefined,
        targetDate: form.targetDate || undefined,
        pointIds: form.pointIds ?? [],
      }
      if (editingId) {
        const updated = await updateGoal(editingId, payload)
        setInfo('已保存')
        // 用服务端最新值替换本地条目
        setGoals((prev) => ({
          ...prev,
          active: prev.active.map((g) =>
            g.goalId === updated.goalId
              ? { ...g, ...updated, statusLabel: TYPE_LABEL[updated.type], subjectLabel: subjectLabels[updated.subject] ?? updated.subject }
              : g,
          ),
        }))
        setEditingId(null)
        setForm(emptyForm())
      } else {
        const created = await createGoal(payload)
        setInfo('已新建')
        // 直接用 created 拼一个最小卡片塞进 active
        setGoals((prev) => ({
          ...prev,
          active: [
            {
              goalId: created.goalId,
              title: created.title,
              type: created.type,
              typeLabel: TYPE_LABEL[created.type],
              subject: created.subject,
              subjectLabel: subjectLabels[created.subject] ?? created.subject,
              targetDate: created.targetDate,
              status: created.status,
              outcome: created.outcome ?? null,
              statusLabel: '进行中',
              percent: Math.round((created.progress?.ratio ?? 0) * 100),
              plannedTasks: created.progress?.plannedTasks ?? 0,
              completedTasks: created.progress?.completedTasks ?? 0,
              completionNote: created.completionNote ?? null,
            },
            ...prev.active,
          ],
        }))
        setForm(emptyForm())
      }
    } catch (err) {
      setError(isNetworkError(err) ? '后端暂不可用，请稍后再试' : (err?.message ?? '保存失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleArchive = async (goal) => {
    setError('')
    setInfo('')
    try {
      const updated = await archiveGoal(goal.goalId)
      // 从 active 移到 finished（用服务端的 progress 刷新百分比）
      setGoals((prev) => {
        const next = prev.active.filter((g) => g.goalId !== updated.goalId)
        return {
          active: next,
          finished: [
            {
              ...goal,
              ...updated,
              statusLabel: '已完成',
              subjectLabel: subjectLabels[updated.subject] ?? updated.subject,
              percent: Math.round((updated.progress?.ratio ?? 0) * 100),
              plannedTasks: updated.progress?.plannedTasks ?? 0,
              completedTasks: updated.progress?.completedTasks ?? 0,
            },
            ...prev.finished,
          ],
        }
      })
      if (editingId === goal.goalId) {
        setEditingId(null)
        setForm(emptyForm())
      }
      setInfo(`已归档「${updated.title}」`)
    } catch (err) {
      setError(isNetworkError(err) ? '后端暂不可用，请稍后再试' : (err?.message ?? '归档失败'))
    }
  }

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          学习目标
          <br />
          <span className="en">Learning Goals</span>
        </h1>

        <form className="goal-form" onSubmit={handleSubmit}>
          <div className="goal-form-row goal-form-row--inline">
            <label className="goal-form-field">
              <span className="goal-form-label">类型 Type</span>
              <select
                className="goal-input"
                value={form.type}
                onChange={handleChange('type')}
              >
                {GOAL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.cn} · {t.en}
                  </option>
                ))}
              </select>
              <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
            </label>

            <label className="goal-form-field">
              <span className="goal-form-label">学科 Subject</span>
              <select
                className="goal-input"
                value={form.subject}
                onChange={handleChange('subject')}
              >
                {SUBJECTS.map((s) => (
                  <option key={s} value={s}>
                    {subjectLabels[s] ?? s}
                  </option>
                ))}
              </select>
              <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
            </label>
          </div>

          <label className="goal-form-field">
            <span className="goal-form-label">标题 Title · 必填</span>
            <input
              className="goal-input"
              type="text"
              maxLength={TITLE_MAX}
              value={form.title}
              onChange={handleChange('title')}
              placeholder="e.g. 两周后期中考试数学 120+"
            />
            <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
          </label>

          <label className="goal-form-field">
            <span className="goal-form-label">描述 Description · 可选</span>
            <textarea
              className="goal-input goal-input--textarea"
              maxLength={DESC_MAX}
              value={form.description}
              onChange={handleChange('description')}
              placeholder="e.g. 函数和数列这两章不太熟，想重点补"
              rows={3}
            />
            <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
          </label>

          <label className="goal-form-field">
            <span className="goal-form-label">目标日期 Target Date · 可选</span>
            <input
              className="goal-input"
              type="date"
              value={form.targetDate}
              onChange={handleChange('targetDate')}
            />
            <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
          </label>

          {points.length > 0 && (
            <div className="goal-form-field">
              <span className="goal-form-label">绑定知识点 Point · 可选（学科联动）</span>
              <div className="goal-points">
                {points.map((p) => {
                  const checked = (form.pointIds ?? []).includes(p.pointId)
                  return (
                    <label key={p.pointId} className="goal-point-chip">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const cur = form.pointIds ?? []
                          const next = checked ? cur.filter((x) => x !== p.pointId) : [...cur, p.pointId]
                          setForm((prev) => ({ ...prev, pointIds: next }))
                        }}
                      />
                      <span>{p.name}</span>
                    </label>
                  )
                })}
              </div>
              <span className="editor-suffix" aria-hidden="true">e<sup>x</sup></span>
            </div>
          )}

          <div className="goal-form-actions">
            {editingId ? (
              <>
                <button type="submit" className="enter-button" disabled={submitting}>
                  {submitting ? '保存中…' : '保存 SAVE'}
                </button>
                <button type="button" className="goal-button-secondary" onClick={handleNew}>
                  取消
                </button>
              </>
            ) : (
              <button type="submit" className="enter-button" disabled={submitting}>
                {submitting ? '新建中…' : '新建 CREATE'}
              </button>
            )}
          </div>
        </form>

        {error && <p className="submit-error">{error}</p>}
        {info && <p className="submit-info">{info}</p>}

        <section className="goal-list">
          <h2 className="goal-list-title">
            进行中
            <span className="goal-list-count">{goals.active.length}</span>
          </h2>
          {loading ? (
            <p className="goal-list-empty">加载中…</p>
          ) : goals.active.length === 0 ? (
            <p className="goal-list-empty">还没有正在进行的目标，先给自己定一个小的吧。</p>
          ) : (
            <ul className="goal-list-items">
              {goals.active.map((goal) => (
                <li
                  key={goal.goalId}
                  className={
                    'goal-list-item' + (editingId === goal.goalId ? ' goal-list-item--editing' : '')
                  }
                >
                  <div className="goal-list-item-head">
                    <h3 className="goal-list-item-title">{goal.title}</h3>
                    <span className="goal-list-item-tag">{goal.typeLabel}</span>
                  </div>
                  <div className="goal-list-item-meta">
                    <span>{goal.subjectLabel}</span>
                    {goal.targetDate ? (
                      <>
                        <span className="meta-divider" />
                        <span>截止 {dayjs(goal.targetDate).format('M 月 D 日')}</span>
                      </>
                    ) : null}
                  </div>
                  <div className="goal-list-item-progress">
                    <div className="goal-progress-track">
                      <div
                        className="goal-progress-fill"
                        style={{ width: `${goal.percent}%` }}
                      />
                    </div>
                    <span className="goal-progress-text">
                      {goal.completedTasks}/{goal.plannedTasks} · {goal.percent}%
                    </span>
                  </div>
                  <div className="goal-list-item-actions">
                    <button
                      type="button"
                      className="goal-button-secondary"
                      onClick={() => handleEdit(goal)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className="goal-button-danger"
                      onClick={() => handleArchive(goal)}
                    >
                      归档
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="goal-list">
          <h2 className="goal-list-title">
            已完成 / 已归档
            <span className="goal-list-count">{goals.finished.length}</span>
          </h2>
          {goals.finished.length === 0 ? (
            <p className="goal-list-empty">历史还很空，慢慢来。</p>
          ) : (
            <ul className="goal-list-items">
              {goals.finished.map((goal) => (
                <li key={goal.goalId} className="goal-list-item goal-list-item--finished">
                  <div className="goal-list-item-head">
                    <h3 className="goal-list-item-title">{goal.title}</h3>
                    <span className="goal-list-item-tag">{goal.typeLabel}</span>
                  </div>
                  <div className="goal-list-item-meta">
                    <span>{goal.subjectLabel}</span>
                    {goal.targetDate ? (
                      <>
                        <span className="meta-divider" />
                        <span>截止 {dayjs(goal.targetDate).format('M 月 D 日')}</span>
                      </>
                    ) : null}
                  </div>
                  <div className="goal-list-item-progress">
                    <div className="goal-progress-track">
                      <div
                        className="goal-progress-fill goal-progress-fill--done"
                        style={{ width: `${goal.percent}%` }}
                      />
                    </div>
                    <span className="goal-progress-text">
                      {goal.completedTasks}/{goal.plannedTasks} · {goal.percent}%
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {editingGoal && (
          <p className="goal-hint">
            正在编辑「{editingGoal.title}」，保存后会留在进行中列表。
          </p>
        )}
      </main>
    </>
  )
}

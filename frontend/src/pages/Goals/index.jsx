import { useEffect, useMemo, useState } from 'react'
import {
  archiveGoal,
  buildGoalTree,
  createGoal,
  fetchGoals,
  updateGoal,
} from '../../services/goals'
import { listExams } from '../../services/exams'
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
  // D6/D29 父子树：'' = 顶层目标
  parentGoalId: '',
  // D49 考试引用：'' = 不关联
  examId: '',
  targetScore: '',
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
    parentGoalId: goal.parentGoalId ?? '',
    examId: goal.examId ?? '',
    targetScore: goal.targetScore === null || goal.targetScore === undefined ? '' : String(goal.targetScore),
  }
}

/**
 * 收集某目标的所有后代 id。
 *
 * 用途：编辑目标时，父目标的候选必须**排除自己与自己的后代**——否则一保存就成环，
 * 后端会拒绝（400），但更好的做法是在选项里就不给它机会。
 */
function collectDescendants(goals, rootId) {
  const out = new Set()
  const walk = (id) => {
    goals.forEach((g) => {
      if (g.parentGoalId === id && !out.has(g.goalId)) {
        out.add(g.goalId)
        walk(g.goalId)
      }
    })
  }
  walk(rootId)
  return out
}

/**
 * 目标卡片。递归渲染子目标（D6/D29：长期目标下挂多个短期子目标）。
 *
 * 缩进表达**从属**，不表达顺序——顺序由优先级/截止日期决定，树不该把两件事混在一起。
 */
function GoalItem({ goal, depth, editingId, exams, onEdit, onArchive }) {
  const exam = goal.examId ? exams.find((e) => e.examId === goal.examId) : null
  const children = goal.children ?? []
  return (
    <>
      <li
        className={
          'goal-list-item' +
          (editingId === goal.goalId ? ' goal-list-item--editing' : '') +
          (depth > 0 ? ' goal-list-item--child' : '')
        }
        style={depth > 0 ? { marginLeft: `${depth * 22}px` } : undefined}
      >
        <div className="goal-list-item-head">
          {depth > 0 && <span className="goal-tree-branch" aria-hidden="true">└</span>}
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
          {exam && (
            <>
              <span className="meta-divider" />
              <span className="goal-exam-link">
                {exam.name}
                {goal.targetScore !== null && goal.targetScore !== undefined
                  ? ` · 目标 ${goal.targetScore}`
                  : ''}
                {/* 「自评 vs 实际」的对照就落在这行：目标是意愿，score 是事实 */}
                {exam.score !== null && exam.score !== undefined
                  ? ` · 实际 ${exam.score}/${exam.fullScore}`
                  : ` · 满分 ${exam.fullScore}`}
              </span>
            </>
          )}
        </div>
        <div className="goal-list-item-progress">
          <div className="goal-progress-track">
            <div className="goal-progress-fill" style={{ width: `${goal.percent}%` }} />
          </div>
          <span className="goal-progress-text">
            {goal.completedTasks}/{goal.plannedTasks} · {goal.percent}%
          </span>
        </div>
        <div className="goal-list-item-actions">
          <button type="button" className="goal-button-secondary" onClick={() => onEdit(goal)}>
            编辑
          </button>
          <button type="button" className="goal-button-danger" onClick={() => onArchive(goal)}>
            归档
          </button>
        </div>
      </li>
      {children.map((kid) => (
        <GoalItem
          key={kid.goalId}
          goal={kid}
          depth={depth + 1}
          editingId={editingId}
          exams={exams}
          onEdit={onEdit}
          onArchive={onArchive}
        />
      ))}
    </>
  )
}

export default function Goals() {
  const [goals, setGoals] = useState({ active: [], finished: [] })
  const [exams, setExams] = useState([])
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
    // 考试列表只用于「关联考试」下拉与卡片上的成绩对照，失败不阻塞目标页
    listExams().then(setExams).catch(() => setExams([]))
  }, [])

  const editingGoal = useMemo(
    () => goals.active.find((g) => g.goalId === editingId) ?? null,
    [goals.active, editingId],
  )

  /** 父目标候选：排除自己 + 自己的后代（防环） */
  const parentCandidates = useMemo(() => {
    if (!editingId) return goals.active
    const banned = collectDescendants(goals.active, editingId)
    banned.add(editingId)
    return goals.active.filter((g) => !banned.has(g.goalId))
  }, [goals.active, editingId])

  /** 目标树（扁平 → 父子嵌套） */
  const activeTree = useMemo(() => buildGoalTree(goals.active), [goals.active])

  const selectedExam = form.examId ? exams.find((e) => e.examId === form.examId) : null

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
    if (form.targetScore !== '') {
      const n = Number(form.targetScore)
      if (Number.isNaN(n) || n < 0) return '目标分数需是非负数'
      if (selectedExam && n > selectedExam.fullScore) {
        return `目标分数不能超过该考试满分（${selectedExam.fullScore}）`
      }
    }
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
        // D6/D29 + D49。显式传 null 表示「顶层 / 不关联」——与「不传=不动」区分。
        parentGoalId: form.parentGoalId || null,
        examId: form.examId || null,
        targetScore: form.targetScore === '' ? null : Number(form.targetScore),
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
              parentGoalId: created.parentGoalId ?? null,
              examId: created.examId ?? null,
              targetScore: created.targetScore ?? null,
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

          <div className="goal-form-row goal-form-row--inline">
            <label className="goal-form-field">
              <span className="goal-form-label">父目标 Parent · 可选</span>
              <select
                className="goal-input"
                value={form.parentGoalId}
                onChange={handleChange('parentGoalId')}
              >
                <option value="">（顶层目标）</option>
                {parentCandidates.map((g) => (
                  <option key={g.goalId} value={g.goalId}>
                    {g.title}
                  </option>
                ))}
              </select>
              {/* 候选里已经排除了自己和自己的后代，成环在选项层就被挡住了 */}
              {editingId && (
                <span className="goal-field-hint">已排除自身与子目标，避免形成环</span>
              )}
            </label>

            <label className="goal-form-field">
              <span className="goal-form-label">关联考试 Exam · 可选</span>
              <select
                className="goal-input"
                value={form.examId}
                onChange={handleChange('examId')}
              >
                <option value="">（不关联）</option>
                {exams.map((e) => (
                  <option key={e.examId} value={e.examId}>
                    {e.name} · {e.examDate}
                    {e.score === null || e.score === undefined
                      ? ` · 满分 ${e.fullScore}`
                      : ` · ${e.score}/${e.fullScore}`}
                  </option>
                ))}
              </select>
            </label>

            <label className="goal-form-field goal-form-field--narrow">
              <span className="goal-form-label">目标分数 · 可选</span>
              <input
                className="goal-input"
                type="number"
                min={0}
                max={selectedExam?.fullScore ?? undefined}
                value={form.targetScore}
                onChange={handleChange('targetScore')}
                placeholder={selectedExam ? `满分 ${selectedExam.fullScore}` : '先选考试'}
                disabled={!selectedExam}
              />
              <span className="goal-field-hint">
                目标只记意愿，考完的实际分数填在考试那边
              </span>
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
              {activeTree.map((goal) => (
                <GoalItem
                  key={goal.goalId}
                  goal={goal}
                  depth={0}
                  editingId={editingId}
                  exams={exams}
                  onEdit={handleEdit}
                  onArchive={handleArchive}
                />
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

/**
 * Chat 结构化卡片渲染器（D22）。
 *
 * 后端卡片协议 schemas.chat.ChatCard = { type, title, payload, display }。
 * payload.action 表明动作，这里按 action 分发执行：
 *   - command（navigate / set_theme）：无副作用，前端直接执行
 *   - confirmation（start_study / create_goal / delete_goal）：落库类，出确认卡，点确认才执行
 *
 * 「#17 第三层」：模型只提案，落库动作绝不直接执行，必须用户点确认。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ChatCard } from './types'
import { createGoal, deleteAllActiveGoals, deleteGoal, fetchGoals } from '@/services/goals'
import { createPlan, localDateString } from '@/services/plans'
import type { GoalType, Subject } from '@/types/api'
import { useTheme } from '../../context/ThemeContext.jsx'

const SUBJECT_CODES: Subject[] = ['SX', 'YY', 'WL', 'HX', 'YW', 'LS', 'DL', 'ZZ', 'SW', 'other']

/** 单个番茄钟默认时长（分钟）。任务总时长按它向上取整拆分，计时页里可调。 */
const POMODORO_MINUTES = 25

/** 中文学科名 → 学科码（后端确定性兜底已保证 code，这里再兜一层模型给中文的情况） */
const SUBJECT_CN_MAP: Record<string, Subject> = {
  数学: 'SX', 英语: 'YY', 英文: 'YY', 物理: 'WL', 化学: 'HX',
  语文: 'YW', 历史: 'LS', 地理: 'DL', 政治: 'ZZ', 生物: 'SW',
}

function asSubject(value: unknown): Subject {
  if (typeof value !== 'string') return 'other'
  if ((SUBJECT_CODES as string[]).includes(value)) return value as Subject
  return SUBJECT_CN_MAP[value] ?? 'other'
}

function CardItems({ items }: { items?: { label: string; value: string }[] }) {
  if (!items || items.length === 0) return null
  return (
    <div className="chat-card-items">
      {items.map((it, i) => (
        <div key={i} className="chat-card-item">
          <span className="chat-card-item-label">{it.label}</span>
          <span className="chat-card-item-value">{it.value}</span>
        </div>
      ))}
    </div>
  )
}

/* ============ command：直接执行（navigate / set_theme） ============ */

function CommandCard({ card }: { card: ChatCard }) {
  const navigate = useNavigate()
  const { setTheme } = useTheme()
  const payload = card.payload || {}
  const ranRef = useRef(false)

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true
    try {
      if (payload.action === 'navigate' && typeof payload.path === 'string' && payload.path) {
        navigate(payload.path)
      } else if (payload.action === 'set_theme' && (payload.theme === 'day' || payload.theme === 'night')) {
        setTheme(payload.theme)
      }
    } catch {
      // 忽略执行失败，不阻断渲染
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="chat-card chat-card-command">
      <div className="chat-card-title">{card.title}</div>
      {card.display?.summary && <div className="chat-card-summary">{card.display.summary}</div>}
    </div>
  )
}

/* ============ confirmation：开始学习（start_study） ============ */

function StartStudyCard({ card }: { card: ChatCard }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const display = card.display
  const items = display?.items
  const payload = card.payload || {}

  // 任务总时长（分钟）
  const planMin = payload.plan?.availableMinutes

  // 番茄钟默认时长 = min(25, 任务时长)：短任务（如 10 分钟）默认番茄钟就是 10，
  // 避免「番茄钟 25」与「拆成 1 个 10 分钟」自相矛盾。用户仍可加减调整。
  const defaultPomodoro =
    typeof planMin === 'number' && planMin > 0 ? Math.min(POMODORO_MINUTES, planMin) : POMODORO_MINUTES
  const [pomodoroMinutes, setPomodoroMinutes] = useState(defaultPomodoro)

  const effPomodoro = Math.max(1, pomodoroMinutes)
  const fullPomodoros =
    typeof planMin === 'number' && planMin > 0 ? Math.floor(planMin / effPomodoro) : 0
  const remMinutes =
    typeof planMin === 'number' && planMin > 0 ? planMin % effPomodoro : 0
  const pomodoroParts: string[] = []
  if (fullPomodoros > 0) pomodoroParts.push(`${fullPomodoros} 个 ${effPomodoro} 分钟`)
  if (remMinutes > 0) pomodoroParts.push(`1 个 ${remMinutes} 分钟`)
  const pomodoroText = pomodoroParts.join(' + ')

  const onConfirm = async () => {
    if (busy || done) return
    setBusy(true)
    setError(null)
    try {
      // 1) 建/复用学习目标
      let goalId: string | undefined
      let goalSubject: Subject | undefined
      const goalIn = payload.goal
      if (goalIn && goalIn.title) {
        goalSubject = asSubject(goalIn.subject)
        let existingId: string | undefined
        try {
          const panel = await fetchGoals()
          existingId = panel.active.find((g) => g.subject === goalSubject)?.goalId
        } catch {
          existingId = undefined
        }
        if (existingId) {
          goalId = existingId
        } else {
          const g = await createGoal({
            type: 'short_term',
            subject: goalSubject,
            title: goalIn.title,
            description: goalIn.description,
          })
          goalId = g.goalId
        }
      }

      // 2) 生成当日计划
      const minutes = typeof planMin === 'number' && Number.isInteger(planMin) ? planMin : 25
      const { plan } = await createPlan({
        planDate: localDateString(),
        availableMinutes: Math.min(600, Math.max(10, minutes)),
        goalIds: goalId ? [goalId] : undefined,
        regenerate: true,
      })
      const first = plan.tasks?.[0]
      if (!first) throw new Error('no_task')

      const subjectCode: Subject =
        goalSubject && goalSubject !== 'other' ? goalSubject : (first.subject as Subject)
      const taskText = typeof payload.task === 'string' && payload.task ? payload.task : first.topic

      setDone(true)
      navigate('/study-timer', {
        state: {
          task: taskText,
          subject: subjectCode,
          taskTotalMinutes: first.estimatedMinutes,
          pomodoroMinutes: effPomodoro,
          planId: plan.planId,
        },
      })
    } catch {
      setError('启动失败，请稍后再试')
      setBusy(false)
    }
  }

  return (
    <div className="chat-card chat-card-confirmation">
      <div className="chat-card-title">{card.title}</div>
      {display?.summary && <div className="chat-card-summary">{display.summary}</div>}
      {typeof planMin === 'number' && planMin > 0 && (
        <div className="chat-card-pomodoro">
          <div className="chat-card-pomodoro-row">
            <span className="chat-card-pomodoro-label">番茄钟</span>
            <div className="chat-card-pomodoro-stepper">
              <button
                type="button"
                className="chat-card-pomodoro-btn"
                onClick={() => setPomodoroMinutes((p) => Math.max(5, p - 5))}
                disabled={busy || done}
                aria-label="减少番茄钟时长"
              >
                −
              </button>
              <input
                className="chat-card-pomodoro-input"
                type="number"
                min={5}
                max={120}
                step={5}
                value={pomodoroMinutes}
                disabled={busy || done}
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10)
                  if (Number.isNaN(n)) return
                  setPomodoroMinutes(Math.min(120, Math.max(5, n)))
                }}
              />
              <button
                type="button"
                className="chat-card-pomodoro-btn"
                onClick={() => setPomodoroMinutes((p) => Math.min(120, p + 5))}
                disabled={busy || done}
                aria-label="增加番茄钟时长"
              >
                +
              </button>
              <span className="chat-card-pomodoro-unit">分钟</span>
            </div>
          </div>
          {pomodoroText && (
            <div className="chat-card-pomodoro-split">任务拆成 <strong>{pomodoroText}</strong></div>
          )}
        </div>
      )}
      <CardItems items={items} />
      {error && <div className="chat-card-error">{error}</div>}
      <button
        type="button"
        className="chat-card-btn"
        onClick={onConfirm}
        disabled={busy || done}
      >
        {done ? '已开始' : busy ? '启动中…' : '开始学习'}
      </button>
    </div>
  )
}

/* ============ confirmation：新建目标（create_goal） ============ */

function CreateGoalCard({ card }: { card: ChatCard }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const items = card.display?.items
  const goal = card.payload?.goal

  const onConfirm = async () => {
    if (busy || done) return
    setBusy(true)
    setError(null)
    try {
      await createGoal({
        type: (goal?.type === 'long_term' ? 'long_term' : 'short_term') as GoalType,
        subject: asSubject(goal?.subject),
        title: goal?.title || '新目标',
        description: goal?.description,
        targetDate: goal?.targetDate || undefined,
      })
      setDone(true)
    } catch {
      setError('创建失败，请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-card chat-card-confirmation">
      <div className="chat-card-title">{card.title}</div>
      {card.display?.summary && <div className="chat-card-summary">{card.display.summary}</div>}
      <CardItems items={items} />
      {error && <div className="chat-card-error">{error}</div>}
      {done ? (
        <div className="chat-card-summary">已创建目标「{goal?.title}」</div>
      ) : (
        <button type="button" className="chat-card-btn" onClick={onConfirm} disabled={busy}>
          {busy ? '创建中…' : '确认创建'}
        </button>
      )}
    </div>
  )
}

/* ============ confirmation：删除目标（delete_goal） ============ */

function DeleteGoalCard({ card }: { card: ChatCard }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(true)
  const [matched, setMatched] = useState<{ goalId: string; title: string } | null>(null)
  const [batchCount, setBatchCount] = useState(0)

  const items = card.display?.items
  const goal = card.payload?.goal
  const title = goal?.title || ''
  const subjectCode = asSubject(goal?.subject)
  // 批量删除：仅当标题**明确**含「所有/全部/未完成/进行中/批量」等批语。⚠️ 空标题绝不进批量——
  // 否则模型想先问「删哪个」却只给空卡时，会被误判成「删光全部进行中目标」（#17 防破甲）。
  const isBatch = /所有|全部|未完成|进行中|批量/.test(title)
  // 信息不足：标题、学科**都**缺才算（模型只给学科时，若该学科只有一个目标仍可安全删）——本次不做任何删除
  const needsInfo = !title && subjectCode === 'other' && !isBatch

  // 挂载时：批量 → 统计 active 数量；单个 → 按标题精确/子串、学科唯一、最后兜底到唯一已归档目标
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const panel = await fetchGoals()
        if (cancelled) return
        if (isBatch) {
          setBatchCount(panel.active.length)
          return
        }
        const all = [...panel.active, ...panel.finished]
        const subject = subjectCode
        const titleExact = title ? all.filter((g) => g.title === title) : []
        const subjGoals = subject !== 'other' ? all.filter((g) => g.subject === subject) : []
        let hit = titleExact[0] ?? null
        if (!hit && title) {
          const partial = all.filter((g) => g.title.includes(title))
          if (partial.length === 1) hit = partial[0]
        }
        if (!hit && subjGoals.length === 1) hit = subjGoals[0]
        // ★ 不确定兜底：用户说「删已归档目标」却未指明学科/标题时，若只有**一个**已归档目标，
        // 就把它作为唯一候选（仍显示真实标题、需用户点确认，符合 #17，不做自动删除）。
        if (!hit && (card.title || '').includes('归档') && panel.finished.length === 1) {
          hit = panel.finished[0]
        }
        if (hit) setMatched({ goalId: hit.goalId, title: hit.title })
      } catch {
        // 拿不到列表则视为无匹配
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onConfirm = async () => {
    if (busy || done) return
    if (!isBatch && !matched) return
    setBusy(true)
    setError(null)
    try {
      if (isBatch) {
        await deleteAllActiveGoals()
      } else if (matched) {
        await deleteGoal(matched.goalId)
      }
      setDone(true)
    } catch {
      setError('删除失败，请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-card chat-card-confirmation">
      <div className="chat-card-title">{card.title}</div>
      {card.display?.summary && <div className="chat-card-summary">{card.display.summary}</div>}
      <CardItems items={items} />
      {error && <div className="chat-card-error">{error}</div>}
      {done ? (
        <div className="chat-card-summary">
          {isBatch ? `已删除 ${batchCount} 个进行中目标` : `已删除目标「${matched?.title ?? title}」`}
        </div>
      ) : loading ? (
        <div className="chat-card-summary">正在查找目标…</div>
      ) : isBatch ? (
        batchCount > 0 ? (
          <button type="button" className="chat-card-btn chat-card-btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? '删除中…' : `确认删除 ${batchCount} 个目标`}
          </button>
        ) : (
          <div className="chat-card-summary">当前没有进行中的目标，无需删除</div>
        )
      ) : matched ? (
        // matched 优先于 needsInfo：未指明目标但只有唯一已归档目标时，兜底已把 matched 指向它，
        // 显示真实标题并让用户确认（#17），而不是停在「信息不足」死胡同。
        <button type="button" className="chat-card-btn chat-card-btn-danger" onClick={onConfirm} disabled={busy}>
          {busy ? '删除中…' : `确认删除「${matched.title}」`}
        </button>
      ) : needsInfo ? (
        <div className="chat-card-summary">缺少要删除的目标信息，本次不会删除任何内容。请告诉我对应的学科与目标名称。</div>
      ) : (
        <div className="chat-card-summary">未找到匹配的目标，可到「学习目标」页手动删除</div>
      )}
    </div>
  )
}

/* ============ 兜底确认卡（未知 confirmation） ============ */

function UnknownConfirmationCard({ card }: { card: ChatCard }) {
  const [done, setDone] = useState(false)
  const items = card.display?.items
  return (
    <div className="chat-card chat-card-confirmation">
      <div className="chat-card-title">{card.title}</div>
      {card.display?.summary && <div className="chat-card-summary">{card.display.summary}</div>}
      <CardItems items={items} />
      {done ? (
        <div className="chat-card-summary">该操作请前往对应功能页完成</div>
      ) : (
        <button type="button" className="chat-card-btn" onClick={() => setDone(true)}>
          知道了
        </button>
      )}
    </div>
  )
}

/* ============ 知识点卡（knowledge_point，多产物） ============ */

function KnowledgeCard({ card }: { card: ChatCard }) {
  const navigate = useNavigate()
  return (
    <div className="chat-card chat-card-knowledge">
      <div className="chat-card-title">{card.title}</div>
      {card.display?.summary && <div className="chat-card-summary">{card.display.summary}</div>}
      <button type="button" className="chat-card-btn" onClick={() => navigate('/knowledge')}>
        查看知识点
      </button>
    </div>
  )
}

/* ============ 分发入口 ============ */

function ConfirmationCard({ card }: { card: ChatCard }) {
  const p = card.payload || {}
  const action = p.action
  if (action === 'start_study') return <StartStudyCard card={card} />
  if (action === 'create_goal') return <CreateGoalCard card={card} />
  if (action === 'delete_goal') return <DeleteGoalCard card={card} />
  // 兼容旧学习卡：无 action 但带 goal/plan/task
  if (!action && (p.goal || p.plan || p.task)) return <StartStudyCard card={card} />
  // 其余未知 confirmation（如旧的「删除目标」类卡）走中性兜底，绝不误显示「开始学习」
  return <UnknownConfirmationCard card={card} />
}

export default function ChatCards({ cards }: { cards: ChatCard[] }) {
  if (!cards || cards.length === 0) return null
  return (
    <>
      {cards.map((card, i) => {
        if (card.type === 'command') {
          return <CommandCard key={i} card={card} />
        }
        if (card.type === 'knowledge_point') {
          return <KnowledgeCard key={i} card={card} />
        }
        if (card.type === 'confirmation' || card.payload?.action) {
          return <ConfirmationCard key={i} card={card} />
        }
        return (
          <div key={i} className="chat-card chat-card-unknown">
            <div className="chat-card-title">{card.title}</div>
          </div>
        )
      })}
    </>
  )
}
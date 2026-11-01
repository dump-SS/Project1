/**
 * D57 · 科学计算器浮窗（F 板块，目标态 §4.10.3 逐句）。
 *
 * §4.10.3（第 870-877 行）要求：
 * - 计算器是浮窗（不是对话内组件）→ 本组件自带 fixed 定位浮窗壳，由
 *   SubjectTools（D56 的 TOOL_REGISTRY 接线点）打开
 * - 右上角两个操作：「添加到对话」与「✕」→ header 右侧两钮
 * - 点击「添加到对话」：切至对话页 + 变输入框引用块「科学计算器 ✕」
 *   （与 §3.9 随手问「添加到主对话」同一形态 = RefChip）→ 由父级
 *   （SubjectTools）负责 navigate + toolRefBus 递送，本组件只交出文本
 * - 注入内容 = 本次唤出计算器的**全部**计算输入与输出 → history 逐条展开
 * - ⚠️ 最后一个计算若未按「=」，其表达式**与结果**也要归拢 → addToChat 时
 *   先对当前未求值表达式补算（第 877 行「需维护 history[]，未求值表达式同样入列」）
 *
 * 说明（两条判断，可被否决）：
 * - DEG 默认 + RAD 可切：高中场景 sin(30)=0.5 是预期
 * - 不做拖动：§4.10.3 未要求（§3.9 的拖动是随手问浮窗的规格）
 */
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, KeyboardEvent } from 'react'
import { safeEvaluate, type AngleMode } from './evaluate'
import { genId } from '@/components/Chat/types'
import styles from './index.module.css'

interface HistoryEntry {
  id: string
  expr: string
  resultText: string
  /** 未按 = 由「添加到对话」自动归拢的条目（§4.10.3 第 877 行） */
  auto?: boolean
}

interface ScientificCalculatorProps {
  onClose: () => void
  /** 交出注入文本（父级切页 + 递引用）；history 为空且无未求值表达式时不会被调用 */
  onAddToChat: (text: string) => void
}

/** 键位 → 插入文本（函数键自动带开括号） */
const KEYS: { label: string; insert?: string; action?: 'equals' | 'clear' | 'backspace'; className?: string }[] = [
  { label: 'C', action: 'clear', className: 'fn' },
  { label: '(', insert: '(' },
  { label: ')', insert: ')' },
  { label: '÷', insert: '÷', className: 'op' },
  { label: '⌫', action: 'backspace', className: 'fn' },
  { label: '7', insert: '7' },
  { label: '8', insert: '8' },
  { label: '9', insert: '9' },
  { label: '×', insert: '×', className: 'op' },
  { label: '^', insert: '^', className: 'op' },
  { label: '4', insert: '4' },
  { label: '5', insert: '5' },
  { label: '6', insert: '6' },
  { label: '−', insert: '−', className: 'op' },
  { label: '√', insert: '√', className: 'op' },
  { label: '1', insert: '1' },
  { label: '2', insert: '2' },
  { label: '3', insert: '3' },
  { label: '+', insert: '+', className: 'op' },
  { label: 'ans', insert: 'ans', className: 'op' },
  { label: '0', insert: '0' },
  { label: '.', insert: '.' },
  { label: '!', insert: '!', className: 'op' },
  { label: 'π', insert: 'π', className: 'op' },
  { label: '=', action: 'equals', className: 'equals' },
  { label: 'sin', insert: 'sin(', className: 'fn' },
  { label: 'cos', insert: 'cos(', className: 'fn' },
  { label: 'tan', insert: 'tan(', className: 'fn' },
  { label: 'log', insert: 'log(', className: 'fn' },
  { label: 'ln', insert: 'ln(', className: 'fn' },
]

/** 这类键在「刚出结果」时开启新表达式，而不是接在结果后面 */
const FRESH_RE = /^[0-9.]$|^π$|^√$|^sin\($|^cos\($|^tan\($|^log\($|^ln\($|^\($/

export default function ScientificCalculator({ onClose, onAddToChat }: ScientificCalculatorProps) {
  const [expr, setExpr] = useState('')
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [angleMode, setAngleMode] = useState<AngleMode>('deg')
  const ansRef = useRef<number | undefined>(undefined)
  /** 显示区当前是否为「= 刚算出的结果」——用于归拢判定与新键位行为 */
  const justEvaluatedRef = useRef(false)
  /** history 的同步镜像：addToChat 合成文本时读它，避免在 setState updater 里跑副作用 */
  const historyRef = useRef<HistoryEntry[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const historyEndRef = useRef<HTMLDivElement>(null)

  /** history 入列（state + ref 同步） */
  const pushHistory = (entry: HistoryEntry) => {
    historyRef.current = [...historyRef.current, entry]
    setHistory(historyRef.current)
  }

  // 新条目入列后滚到历史底部
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ block: 'end' })
  }, [history])

  /** 在光标处插入文本（键盘/键位两条输入路径共用） */
  const insertAtCursor = (text: string) => {
    const el = inputRef.current
    const current = justEvaluatedRef.current && FRESH_RE.test(text) ? '' : expr
    if (!el) {
      setExpr(current + text)
    } else {
      const start = el.selectionStart ?? current.length
      const end = el.selectionEnd ?? current.length
      const next = current.slice(0, start) + text + current.slice(end)
      setExpr(next)
      requestAnimationFrame(() => {
        el.focus()
        const caret = start + text.length
        el.setSelectionRange(caret, caret)
      })
    }
    justEvaluatedRef.current = false
    setError(null)
  }

  const backspace = () => {
    const el = inputRef.current
    const current = justEvaluatedRef.current ? '' : expr
    if (!el || el.selectionStart === null || el.selectionStart !== el.selectionEnd) {
      setExpr(current.slice(0, -1))
    } else if (el.selectionStart > 0) {
      const caret = el.selectionStart
      setExpr(current.slice(0, caret - 1) + current.slice(caret))
      requestAnimationFrame(() => {
        el.focus()
        el.setSelectionRange(caret - 1, caret - 1)
      })
    }
    justEvaluatedRef.current = false
    setError(null)
  }

  const clearAll = () => {
    setExpr('')
    setError(null)
    justEvaluatedRef.current = false
  }

  const equals = () => {
    const raw = expr.trim()
    if (!raw) return
    const outcome = safeEvaluate(raw, { angleMode, ans: ansRef.current })
    if (outcome.ok && outcome.value !== undefined) {
      const resultText = String(outcome.value)
      pushHistory({ id: genId('calc'), expr: raw, resultText })
      ansRef.current = outcome.value
      setExpr(resultText)
      justEvaluatedRef.current = true
      setError(null)
    } else {
      // 出错不清输入：让学生改而不是重打
      setError(outcome.error ?? '无法计算该表达式')
    }
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      equals()
    }
  }

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    setExpr(e.target.value)
    justEvaluatedRef.current = false
    setError(null)
  }

  /**
   * 「添加到对话」（§4.10.3 第 873-877 行）：注入 = 全部计算输入与输出。
   * 未按 = 的当前表达式先补算入列（求不出则标「未算出」——表达式仍要归拢）。
   */
  const addToChat = () => {
    const pending = expr.trim()
    if (pending && !justEvaluatedRef.current) {
      const outcome = safeEvaluate(pending, { angleMode, ans: ansRef.current })
      pushHistory({
        id: genId('calc'),
        expr: pending,
        resultText: outcome.ok && outcome.value !== undefined ? String(outcome.value) : '（未算出）',
        auto: true,
      })
    }
    if (historyRef.current.length === 0) return
    const lines = historyRef.current.map(
      (h, i) => `${i + 1}) ${h.expr} = ${h.resultText}${h.auto ? '（未按=，自动归拢）' : ''}`,
    )
    onAddToChat(lines.join('\n'))
  }

  return (
    <section className={styles.calc} role="dialog" aria-label="科学计算器" data-testid="calculator-float">
      <header className={styles.head}>
        <span className={styles.title}>科学计算器</span>
        <div className={styles.mode} role="group" aria-label="角度单位">
          <button
            type="button"
            className={`${styles.modeBtn} ${angleMode === 'deg' ? styles.modeOn : ''}`}
            onClick={() => setAngleMode('deg')}
            aria-pressed={angleMode === 'deg'}
          >
            DEG
          </button>
          <button
            type="button"
            className={`${styles.modeBtn} ${angleMode === 'rad' ? styles.modeOn : ''}`}
            onClick={() => setAngleMode('rad')}
            aria-pressed={angleMode === 'rad'}
          >
            RAD
          </button>
        </div>
        <div className={styles.spacer} />
        {/* §4.10.3 第 872 行：右上角两个操作 */}
        <button type="button" className={styles.addBtn} onClick={addToChat} disabled={history.length === 0 && !expr.trim()}>
          添加到对话
        </button>
        <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="关闭计算器">
          ✕
        </button>
      </header>

      <div className={styles.display}>
        <div className={styles.history} aria-label="计算历史">
          {history.length === 0 && <p className={styles.historyEmpty}>算过的式子会留在这里，「添加到对话」会带走全部历史</p>}
          {history.map((h) => (
            <p key={h.id} className={styles.historyLine}>
              <span className={styles.historyExpr}>{h.expr}</span>
              <span className={styles.historyEq}>=</span>
              <span className={styles.historyVal}>{h.resultText}</span>
              {h.auto && <span className={styles.historyAuto}>未按=·自动归拢</span>}
            </p>
          ))}
          <div ref={historyEndRef} />
        </div>
        <input
          ref={inputRef}
          className={styles.entry}
          value={expr}
          onChange={onChange}
          onKeyDown={onKey}
          placeholder="输入表达式，Enter 或 = 求值"
          aria-label="计算器输入"
          spellCheck={false}
          data-testid="calculator-input"
        />
        <p className={`${styles.feedback} ${error ? styles.feedbackError : ''}`} role="status">
          {error ?? ''}
        </p>
      </div>

      <div className={styles.keypad}>
        {KEYS.map((k) => (
          <button
            key={k.label}
            type="button"
            className={`${styles.key} ${k.className ? styles[k.className as 'op' | 'fn' | 'equals'] ?? '' : ''}`}
            onClick={() => {
              if (k.action === 'equals') equals()
              else if (k.action === 'clear') clearAll()
              else if (k.action === 'backspace') backspace()
              else if (k.insert) insertAtCursor(k.insert)
            }}
          >
            {k.label}
          </button>
        ))}
      </div>
    </section>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'

function formatTime(totalSeconds) {
  if (totalSeconds <= 0) return '00:00'
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function DurationField({ label, value, min, max, onCommit }) {
  const [draft, setDraft] = useState(String(value))

  const commit = () => {
    let n = parseInt(draft, 10)
    if (Number.isNaN(n)) n = value
    n = Math.min(max, Math.max(min, n))
    setDraft(String(n))
    onCommit(n)
  }

  return (
    <label className="duration-field">
      <span className="duration-label">{label}</span>
      <input
        className="duration-input"
        type="number"
        min={min}
        max={max}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
      />
      <span className="duration-unit">分</span>
    </label>
  )
}

function CompletionPopup({ task, onOk, onRestart }) {
  return (
    <div className="completion-pop">
      <span className="pop-title">任务完成</span>
      <span className="pop-text">「{task}」已完成</span>
      <span className="pop-actions">
        <button className="pop-ok" onClick={onOk}>OK</button>
        <button className="pop-restart" onClick={onRestart}>再学一轮</button>
      </span>
    </div>
  )
}

export default function App() {
  const [task, setTask] = useState('复习函数章节')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(task)

  const [mode, setMode] = useState('focus')
  const [focusMinutes, setFocusMinutes] = useState(25)
  const [breakMinutes, setBreakMinutes] = useState(5)
  const [remaining, setRemaining] = useState(25 * 60)
  const [isRunning, setIsRunning] = useState(false)
  const [showDone, setShowDone] = useState(false)

  const timerRef = useRef(null)

  const totalSeconds = (mode === 'focus' ? focusMinutes : breakMinutes) * 60

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setIsRunning(false)
  }, [])

  const startTimer = useCallback(() => {
    if (totalSeconds <= 0) return
    if (timerRef.current) return
    setIsRunning(true)
    timerRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current)
          timerRef.current = null
          setIsRunning(false)
          if (mode === 'focus') setShowDone(true)
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }, [mode, totalSeconds])

  useEffect(() => {
    stopTimer()
    setRemaining(totalSeconds)
  }, [mode, totalSeconds, stopTimer])

  const handleRestart = () => {
    setShowDone(false)
    setMode('focus')
    setRemaining(focusMinutes * 60)
  }

  const handleSaveTask = () => {
    const next = draft.trim()
    if (next) setTask(next)
    setDraft(next || task)
    setEditing(false)
  }

  const handleCancelTask = () => {
    setDraft(task)
    setEditing(false)
  }

  return (
    <div className="app">
      <div className="bg-sky" aria-hidden="true" />

      <header className="topbar">
        <span className="brand">静心·学习</span>

        <div className="task-inline">
          {editing ? (
            <div className="task-edit">
              <input
                className="task-input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={40}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveTask()
                  if (e.key === 'Escape') handleCancelTask()
                }}
              />
              <button className="icon-btn" onClick={handleSaveTask}>保存</button>
              <button className="icon-btn ghost" onClick={handleCancelTask}>取消</button>
            </div>
          ) : (
            <div className="task-view">
              <span className="task-label">任务</span>
              <span className="task-title">{task}</span>
              <button className="icon-btn ghost" onClick={() => setEditing(true)}>编辑</button>
            </div>
          )}
        </div>

        <div className="mode-tabs">
          <button
            className={`mode-tab ${mode === 'focus' ? 'active' : ''}`}
            onClick={() => setMode('focus')}
          >
            专注
          </button>
          <button
            className={`mode-tab ${mode === 'break' ? 'active' : ''}`}
            onClick={() => setMode('break')}
          >
            休息
          </button>
        </div>

        <DurationField label="专注" value={focusMinutes} min={0} max={180} onCommit={setFocusMinutes} />
        <DurationField label="休息" value={breakMinutes} min={0} max={60} onCommit={setBreakMinutes} />

        <span className="time-big">{formatTime(remaining)}</span>

        <div className="controls">
          {!isRunning ? (
            <button
              className="btn primary"
              disabled={totalSeconds <= 0 && remaining <= 0}
              onClick={remaining === 0 ? () => setRemaining(totalSeconds) : startTimer}
            >
              {remaining === 0 ? '重新开始' : remaining === totalSeconds ? '开始' : '继续'}
            </button>
          ) : (
            <button className="btn ghost" onClick={stopTimer}>
              暂停
            </button>
          )}
          <button
            className="btn ghost"
            onClick={() => {
              stopTimer()
              setRemaining(totalSeconds)
            }}
          >
            重置
          </button>
        </div>
      </header>

      <main className="center-stage">
        <h1 className="epochx">EpochX</h1>
      </main>

      {showDone && (
        <CompletionPopup
          task={task}
          onOk={() => setShowDone(false)}
          onRestart={handleRestart}
        />
      )}
    </div>
  )
}

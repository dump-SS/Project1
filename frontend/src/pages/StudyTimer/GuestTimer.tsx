/**
 * 游客计时（D1 / D43）——「打算、计时」两条非 AI 路径之一。
 *
 * 为什么是**独立组件**而不是给 StudyTimer 加 if：
 * 正版计时页的会话真相源在服务端（D30：刷新/断线按 mode 恢复、心跳僵尸治理、
 * 结束与落记录是一个原子请求）。游客**不落库**，这些语义一个都不该触发，
 * 硬塞进同一份状态机只会让两条路径互相污染。这里给游客一条**自包含**的
 * 本地计时：只用内存与 setInterval，关掉页面即消失，不调用任何接口。
 *
 * 页面上明说三件事：游客不保存数据、不能用 AI 功能、登录后试用数据会清空。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import styles from './GuestTimer.module.css'
import { subjectLabels } from '../../styles/theme'
import type { Subject } from '../../types/api'

type Mode = 'countdown' | 'countup'

function formatTime(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds || 0))
  const m = Math.floor(s / 60)
  const rest = s % 60
  return `${String(m).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

export default function GuestTimer() {
  const [params] = useSearchParams()
  const targetMinutes = Math.min(600, Math.max(10, Number(params.get('minutes')) || 25))
  const subject = params.get('subject') || ''

  const [mode, setMode] = useState<Mode>('countdown')
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [finished, setFinished] = useState(false)
  const timerRef = useRef<number | null>(null)

  // 本地计时：只累加内存里的秒数（页面一关就没了，符合「游客不保存」口径）
  useEffect(() => {
    if (!running) return
    timerRef.current = window.setInterval(() => {
      setElapsed((s) => s + 1)
    }, 1000)
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [running])

  const targetSeconds = targetMinutes * 60
  const remaining = Math.max(0, targetSeconds - elapsed)
  const reached = mode === 'countdown' && remaining === 0

  const display = mode === 'countdown' ? remaining : elapsed

  const handleFinish = useCallback(() => {
    setRunning(false)
    setFinished(true)
  }, [])

  const handleRestart = useCallback(() => {
    setElapsed(0)
    setFinished(false)
    setRunning(false)
  }, [])

  const subjectLabel = subject ? (subjectLabels[subject as Subject] ?? subject) : ''

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>
        专注计时
        <span className={styles.en}>Guest Trial</span>
      </h1>

      <div className={styles.note} role="note">
        <strong>游客试用中</strong>
        <span>本次计时不会保存到任何账号，也不能使用 AI 功能。</span>
        <Link to="/login" className={styles.noteLink}>登录 / 注册</Link>
        <span>后可保存记录并获得状态评估。</span>
      </div>

      {!finished ? (
        <>
          <div className={styles.modeRow} role="radiogroup" aria-label="计时模式">
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'countdown'}
              className={`${styles.modeBtn} ${mode === 'countdown' ? styles.modeBtnActive : ''}`}
              onClick={() => { setMode('countdown'); setElapsed(0); setRunning(false) }}
              disabled={running}
            >
              倒计时 {targetMinutes} 分钟
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'countup'}
              className={`${styles.modeBtn} ${mode === 'countup' ? styles.modeBtnActive : ''}`}
              onClick={() => { setMode('countup'); setElapsed(0); setRunning(false) }}
              disabled={running}
            >
              正计时
            </button>
          </div>

          {subjectLabel && <p className={styles.subject}>科目：{subjectLabel}</p>}

          <div className={`${styles.clock} ${reached ? styles.clockReached : ''}`} aria-live="polite">
            {formatTime(display)}
          </div>
          {reached && <p className={styles.reached}>已到点——你可以继续，也可以结束本次专注</p>}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={() => setRunning((v) => !v)}
            >
              {running ? '暂停' : elapsed > 0 ? '继续' : '开始'}
            </button>
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={handleFinish}
              disabled={elapsed === 0}
            >
              结束本次
            </button>
          </div>
        </>
      ) : (
        <div className={styles.result} role="status">
          <p className={styles.resultTitle}>本次专注 {Math.max(1, Math.round(elapsed / 60))} 分钟</p>
          <p className={styles.resultText}>
            游客试用：这段记录<strong>没有</strong>保存到任何账号，关闭页面即消失。
            登录后计时会存档，并解锁状态评估、建议与 AI 能力。
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryBtn} to="/login">登录保存学习记录</Link>
            <button type="button" className={styles.ghostBtn} onClick={handleRestart}>
              再试一次
            </button>
          </div>
        </div>
      )}
    </main>
  )
}

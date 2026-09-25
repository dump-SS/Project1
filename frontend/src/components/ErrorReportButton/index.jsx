/**
 * 消息级报错按钮（#46 第②处入口）—— G 板块可复用组件。
 *
 * 挂在每条模型输出旁，点击展开一行描述框，提交时带上下文定位问题：
 *   <ErrorReportButton messageId={msg.id} intent={msg.intent} context={{ role: 'assistant' }} />
 *
 * ⚠️ 上下文只放结构化信息（角色/意图/卡片类型等），**不传对话原文流水**
 * （与 D45「不做对话历史 / 原文短期留存」口径分开）。
 * B 板块重写 Chat 时在模型输出气泡上挂载本组件；设置页常驻入口另见 Settings/GovernancePanel。
 */
import { useRef, useState } from 'react'
import { postErrorReport } from '@/services/feedback'
import { isNetworkError } from '@/services/http'
import styles from './index.module.css'

export default function ErrorReportButton({ messageId, intent, context, label = '报错' }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  const toggle = () => {
    setOpen((v) => !v)
    setDone(false)
    setError('')
    if (!open) setTimeout(() => inputRef.current?.focus(), 0)
  }

  const submit = async () => {
    const description = text.trim()
    if (!description) return
    setSubmitting(true)
    setError('')
    try {
      await postErrorReport({ messageId, intent, description, context })
      setDone(true)
      setText('')
      setTimeout(() => setOpen(false), 1200)
    } catch (err) {
      setError(isNetworkError(err) ? '网络不可用，请稍后再试' : (err?.message ?? '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={`${styles.btn}${open ? styles.btnOpen : ''}`}
        onClick={toggle}
        aria-expanded={open}
        title="这条回答有问题？告诉我们"
      >
        {done ? '已收到，谢谢' : label}
      </button>
      {open && !done ? (
        <span className={styles.pop}>
          <textarea
            ref={inputRef}
            className={styles.textarea}
            rows={2}
            maxLength={2000}
            placeholder="哪里不对？（可选填，我们会结合这条消息的上下文排查）"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
            }}
          />
          <span className={styles.popActions}>
            {error ? <span className={styles.popError}>{error}</span> : null}
            <button type="button" className={styles.send} disabled={submitting || !text.trim()} onClick={submit}>
              {submitting ? '提交中…' : '提交'}
            </button>
          </span>
        </span>
      ) : null}
    </span>
  )
}

import { useEffect, useState } from 'react'
import styles from './index.module.css'
import { revokeGuardianAuthorization, submitGuardianAuthorization } from '../../services/guardian'
import { getMe } from '../../services/user'
import type { GuardianAuthorizationStatus, User } from '../../types/api'

const STATUS_INFO: Record<GuardianAuthorizationStatus, { title: string; text: string }> = {
  pending: { title: '等待监护人确认', text: '确认请求已发送，请监护人查收邮件/短信并点击链接完成授权。' },
  active: { title: '已授权', text: '监护人已确认，AI 建议与复盘功能可用。' },
  revoked: { title: '已撤销', text: '授权已撤销，账号进入只读状态，AI 建议与复盘功能暂停。' },
  expired: { title: '授权已过期', text: '授权已过期，请重新提交监护人联系方式。' },
}

function isValidEmail(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

function isValidPhone(v: string): boolean {
  return /^\+?[\d\s-]{6,20}$/.test(v)
}

export default function GuardianAuthPage() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [fieldErr, setFieldErr] = useState('')
  const [tip, setTip] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const loadUser = () => {
    setLoading(true)
    setLoadError(null)
    getMe()
      .then((data) => {
        setUser(data)
        setEmail(data.guardianAuthorization?.status === 'pending' ? '' : email)
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : '加载用户资料失败'))
      .finally(() => setLoading(false))
  }

  useEffect(loadUser, [])

  const status = user?.guardianAuthorization?.status ?? 'revoked'
  const info = STATUS_INFO[status] ?? STATUS_INFO.revoked

  const handleSubmit = async () => {
    const e = email.trim()
    const p = phone.trim()
    if (!e && !p) {
      setFieldErr('请至少填写监护人邮箱或手机号')
      return
    }
    if (e && !isValidEmail(e)) {
      setFieldErr('邮箱格式不正确')
      return
    }
    if (p && !isValidPhone(p)) {
      setFieldErr('手机号格式不正确')
      return
    }
    setFieldErr('')
    setTip(null)
    setSubmitting(true)
    try {
      await submitGuardianAuthorization({
        guardianEmail: e || undefined,
        guardianPhone: p || undefined,
      })
      setTip({ type: 'success', msg: '确认请求已发送，请等待监护人确认。' })
      loadUser()
    } catch (err) {
      setTip({ type: 'error', msg: err instanceof Error ? err.message : '提交失败，请稍后再试' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevoke = async () => {
    if (!window.confirm('确定撤销监护人授权吗？撤销后账号进入只读，AI 建议与复盘功能将暂停。')) return
    setTip(null)
    setSubmitting(true)
    try {
      await revokeGuardianAuthorization()
      setTip({ type: 'success', msg: '授权已撤销，账号进入只读状态。' })
      loadUser()
    } catch (err) {
      setTip({ type: 'error', msg: err instanceof Error ? err.message : '撤销失败，请稍后再试' })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className={styles.page}><p className={styles.loading}>加载中…</p></div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>监护人授权</h1>
        <p className={styles.subtitle}>为了使用 AI 建议/复盘功能，需要监护人确认（PRD 8.1 合规底线）。</p>
      </header>

      {loadError && <p className={styles.error}>{loadError}</p>}

      <section className={styles.card}>
        <div className={styles.statusRow}>
          <span className={`${styles.statusTag} ${styles[`status_${status}`] ?? ''}`}>{info.title}</span>
          <span className={styles.statusText}>{info.text}</span>
          {status === 'active' && user?.guardianAuthorization?.expiresAt && (
            <span className={styles.expire}>有效期至 {new Date(user.guardianAuthorization.expiresAt).toLocaleDateString()}</span>
          )}
        </div>

        {(status === 'revoked' || status === 'expired') && (
          <div className={styles.form}>
            <label className={styles.field}>
              <span className={styles.label}>监护人邮箱</span>
              <input
                className={styles.textInput}
                value={email}
                placeholder="guardian@example.com"
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>监护人手机号</span>
              <input
                className={styles.textInput}
                value={phone}
                placeholder="13800138000"
                onChange={(e) => setPhone(e.target.value)}
              />
            </label>
            <p className={styles.hint}>邮箱与手机号二选一即可。</p>
            {fieldErr && <p className={styles.error}>{fieldErr}</p>}
            {tip && <p className={tip.type === 'success' ? styles.success : styles.error}>{tip.msg}</p>}
            <button
              type="button"
              className={styles.submitBtn}
              disabled={submitting}
              onClick={handleSubmit}
            >
              {submitting ? '提交中…' : '发送确认请求'}
            </button>
          </div>
        )}

        {status === 'pending' && (
          <p className={styles.pendingText}>{tip?.msg ?? info.text}</p>
        )}

        {status === 'active' && (
          <div className={styles.form}>
            {tip && <p className={tip.type === 'success' ? styles.success : styles.error}>{tip.msg}</p>}
            <button
              type="button"
              className={styles.dangerBtn}
              disabled={submitting}
              onClick={handleRevoke}
            >
              {submitting ? '处理中…' : '撤销授权'}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

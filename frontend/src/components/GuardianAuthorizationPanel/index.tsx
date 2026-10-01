/**
 * 监护人授权面板（D41，「页面一处」的实现）。
 *
 * 两处入口都渲染同一个面板，避免出现两套会漂移的 UI：
 *  ① 激活式建档流程（未满 14 岁时强制门槛）；
 *  ② 设置 → 授权与隐私（常驻）。
 *
 * 状态机（后端为准）：pending → active → revoked → 重新提交 pending；
 * 提交后 MVP 不发真邮件，后端直接返回一次性 token，前端拼确认链接给演示者/监护人点开
 * （监护人点开后看到的是后端渲染的结果页，见 routes/user.py::_guardian_result_page）。
 */
import { useCallback, useEffect, useState } from 'react'
import { getMe } from '../../services/user'
import {
  buildGuardianConfirmUrl,
  revokeGuardianAuthorization,
  submitGuardianAuthorization,
} from '../../services/guardian'
import type { GuardianAuthorizationStatus } from '../../types/api'
import styles from './index.module.css'

const STATUS_TEXT: Record<GuardianAuthorizationStatus, string> = {
  pending: '待确认',
  active: '已授权',
  revoked: '已撤销',
  expired: '已过期',
}

export interface GuardianAuthorizationPanelProps {
  /** 授权状态变化后通知外层（建档流程据此推进到下一步） */
  onStatusChange?: (status: GuardianAuthorizationStatus) => void
  /** 紧凑形态：建档流程内嵌时不重复大标题 */
  compact?: boolean
}

export default function GuardianAuthorizationPanel({
  onStatusChange,
  compact = false,
}: GuardianAuthorizationPanelProps) {
  const [status, setStatus] = useState<GuardianAuthorizationStatus>('pending')
  const [expiresAt, setExpiresAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [contact, setContact] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [confirmUrl, setConfirmUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [tip, setTip] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const refresh = useCallback(async () => {
    try {
      const me = await getMe()
      const g = me.guardianAuthorization
      setStatus(g.status)
      setExpiresAt(g.expiresAt ?? null)
      onStatusChange?.(g.status)
    } catch {
      setTip({ type: 'err', text: '读取授权状态失败，请稍后再试' })
    } finally {
      setLoading(false)
    }
  }, [onStatusChange])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleSubmit = async () => {
    const value = contact.trim()
    if (!value) {
      setTip({ type: 'err', text: '请填写监护人的邮箱或手机号' })
      return
    }
    setSubmitting(true)
    setTip(null)
    try {
      // 邮箱/手机二选一：含 @ 视为邮箱
      const body = value.includes('@') ? { guardianEmail: value } : { guardianPhone: value }
      const result = await submitGuardianAuthorization(body)
      setConfirmUrl(buildGuardianConfirmUrl(result.confirmToken))
      setStatus('pending')
      onStatusChange?.('pending')
      setTip({
        type: 'ok',
        text: '已向监护人发出确认请求（pilot 演示期不发邮件，请把下方链接转给监护人点开）。',
      })
    } catch (e) {
      setTip({ type: 'err', text: e instanceof Error ? e.message : '提交失败，请稍后再试' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevoke = async () => {
    setSubmitting(true)
    setTip(null)
    try {
      await revokeGuardianAuthorization()
      setConfirmUrl('')
      setStatus('revoked')
      onStatusChange?.('revoked')
      setTip({ type: 'ok', text: '已撤销授权，账号进入只读状态。' })
    } catch (e) {
      setTip({ type: 'err', text: e instanceof Error ? e.message : '撤销失败，请稍后再试' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(confirmUrl)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setTip({ type: 'err', text: '复制失败，请手动选中链接复制' })
    }
  }

  return (
    <section className={styles.panel} aria-label="监护人授权">
      {!compact && (
        <header className={styles.head}>
          <h3 className={styles.title}>监护人授权</h3>
          <p className={styles.subtitle}>
            未满 14 周岁的账号必须完成监护人确认后才能建档与使用；授权有效期 12 个月，可随时撤销。
          </p>
        </header>
      )}

      <div className={styles.statusRow}>
        <span className={`${styles.badge} ${styles[`badge_${status}`] ?? ''}`}>
          {STATUS_TEXT[status] ?? status}
        </span>
        {status === 'active' && expiresAt && (
          <span className={styles.expires}>
            到期：{new Date(expiresAt).toLocaleDateString('zh-CN')}
          </span>
        )}
        <button type="button" className={styles.linkBtn} onClick={refresh} disabled={loading}>
          刷新状态
        </button>
      </div>

      {status !== 'active' && (
        <div className={styles.form}>
          <label className={styles.label} htmlFor="guardian-contact">
            监护人联系方式
          </label>
          <input
            id="guardian-contact"
            className={styles.input}
            placeholder="监护人邮箱或手机号（二选一）"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            autoComplete="off"
          />
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? '提交中…' : '发送确认请求'}
          </button>
        </div>
      )}

      {confirmUrl && status !== 'active' && (
        <div className={styles.confirmBox}>
          <p className={styles.confirmHint}>
            把这条链接发给监护人，请他在浏览器中打开并确认（链接一次性有效）：
          </p>
          <code className={styles.confirmUrl}>{confirmUrl}</code>
          <button type="button" className={styles.ghostBtn} onClick={handleCopy}>
            {copied ? '已复制' : '复制链接'}
          </button>
        </div>
      )}

      {status === 'active' && (
        <button type="button" className={styles.dangerBtn} onClick={handleRevoke} disabled={submitting}>
          撤销授权
        </button>
      )}

      {tip && (
        <p className={tip.type === 'ok' ? styles.okText : styles.errText} role="status">
          {tip.text}
        </p>
      )}

      <p className={styles.footnote}>
        EpochX 由学生团队开发，本页文案未经专业法律审核（pilot 口径）。
      </p>
    </section>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './index.module.css'
import type { GuardianAuthorizationStatus } from '../../types/api'
import { getMe } from '../../services/user'
import { revokeGuardianAuthorization, submitGuardianAuthorization } from '../../services/guardian'
import { isNetworkError } from '../../services/http'

/**
 * 监护人授权页（PRD 8.1 合规底线）
 *
 * 该页面是面向监护人与被监护学生（未成年）的合规授权页。
 * 根据《个人信息保护法》及未成年人保护相关要求，AI 建议/复盘功能需经监护人确认。
 *
 * 已接入真实后端（openapi.yaml 0.5 节）：
 * - GET    /me                        读取真实授权状态（pending/active/revoked/expired）
 * - POST   /me/guardian-authorization 提交监护人联系方式（邮箱/手机二选一，202）
 * - DELETE /me/guardian-authorization 撤销授权（204）
 *
 * 注意：后端把「未提交」与「待确认」都返回 pending，页面只有在本会话提交成功后才
 * 展示"等待确认"；刷新后回到提交表单（重复提交幂等，后端会重置 token）。
 * 「演示：…」按钮仅供产品走查 —— MVP 阶段后端不真发邮件，确认链接 token 页面拿不到。
 */

/** 统一提取错误文案：网络不可达 / 后端业务错误 / 兜底 */
function errMsg(err: unknown): string {
  if (isNetworkError(err)) return '无法连接服务器，请确认后端已启动'
  if (err instanceof Error && err.message) return err.message
  return '操作失败，请稍后重试'
}

type LogEntry = { at: string; action: string; detail?: string }

const STATUS_INFO: Record<GuardianAuthorizationStatus, { title: string; text: string; tone: string }> = {
  pending: { title: '等待监护人确认', text: '确认请求已发送，请监护人查收邮件/短信并点击链接完成授权。', tone: 'pending' },
  active: { title: '已授权', text: '监护人已确认，AI 建议与复盘功能可用。', tone: 'active' },
  revoked: { title: '尚未授权', text: '当前账号未提交监护人授权，AI 建议与复盘功能受限。请提交监护人邮箱或手机号。', tone: 'revoked' },
  expired: { title: '授权已过期', text: '授权已过期，请重新提交监护人联系方式。', tone: 'expired' },
}

function isValidEmail(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

function isValidPhone(v: string): boolean {
  return /^\+?[\d\s-]{6,20}$/.test(v)
}

function nowStr() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export default function GuardianAuthPage() {
  // 状态机（默认 revoked：后端 pending 在未提交时也按表单态展示，见文件头注释）
  const [status, setStatus] = useState<GuardianAuthorizationStatus>('revoked')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [channel, setChannel] = useState<'email' | 'phone'>('email') // 发送通道（邮箱/手机二选一）
  const [agreed, setAgreed] = useState(false) // 同意《监护人授权协议》勾选
  const [fieldErr, setFieldErr] = useState('')
  const [tip, setTip] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true) // 首屏从 GET /me 读取真实状态
  const [logs, setLogs] = useState<LogEntry[]>([])
  const submittedThisSession = useRef(false) // 本会话是否提交过（区分「待确认」与「未提交」）

  // 授权到期时间：active 时展示，来自后端 GET /me 的 expiresAt
  const [expiresAt, setExpiresAt] = useState<string | null>(null)

  const info = STATUS_INFO[status]

  // 首屏：从后端读取真实授权状态；失败则保持表单态并提示
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await getMe()
        if (cancelled) return
        const g = me.guardianAuthorization
        if (g.expiresAt) setExpiresAt(g.expiresAt)
        // 后端把「未提交」也归为 pending，只有本会话提交过才展示"等待确认"
        if (g.status !== 'pending' || submittedThisSession.current) {
          setStatus(g.status)
        }
        setLogs([{ at: nowStr(), action: 'INIT', detail: `后端授权状态：${g.status}` }])
      } catch (err) {
        if (cancelled) return
        setLogs([{ at: nowStr(), action: 'INIT_FAIL', detail: errMsg(err) }])
        setTip({ type: 'error', msg: `读取授权状态失败：${errMsg(err)}` })
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const channelHint = useMemo(() => {
    if (channel === 'email') {
      return '将向该邮箱发送一次性确认链接，24 小时内有效'
    }
    return '将向该手机号发送 6 位短信验证码，10 分钟内有效'
  }, [channel])

  const appendLog = (action: string, detail?: string) => {
    setLogs((prev) => [{ at: nowStr(), action, detail }, ...prev].slice(0, 6))
  }

  const handleSubmit = async () => {
    const e = email.trim()
    const p = phone.trim()
    if (!agreed) {
      setFieldErr('请先勾选同意《监护人授权协议》')
      return
    }
    if (channel === 'email') {
      if (!e) {
        setFieldErr('请填写监护人邮箱')
        return
      }
      if (!isValidEmail(e)) {
        setFieldErr('邮箱格式不正确')
        return
      }
    } else {
      if (!p) {
        setFieldErr('请填写监护人手机号')
        return
      }
      if (!isValidPhone(p)) {
        setFieldErr('手机号格式不正确')
        return
      }
    }
    setFieldErr('')
    setTip(null)
    setSubmitting(true)
    try {
      await submitGuardianAuthorization(
        channel === 'email' ? { guardianEmail: e } : { guardianPhone: p },
      )
      submittedThisSession.current = true
      setStatus('pending')
      setTip({ type: 'success', msg: '确认请求已发送，请等待监护人确认。' })
      appendLog('SUBMIT', channel === 'email' ? `邮箱 ${e}` : `手机号 ${p}`)
    } catch (err) {
      setTip({ type: 'error', msg: `提交失败：${errMsg(err)}` })
      appendLog('SUBMIT_FAIL', errMsg(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleSimulateConfirm = () => {
    // 演示用：真实环境由监护人点击邮件/短信中的确认链接完成
    // （GET /guardian-authorization/confirm?token=…，无需登录）。MVP 阶段后端不真发邮件，
    // token 页面拿不到，这里仅在本地模拟确认结果，刷新后以后端实际状态为准。
    setStatus('active')
    setExpiresAt(new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString())
    setTip({ type: 'success', msg: '演示模式：已模拟监护人确认。真实确认需监护人点击收到的确认链接。' })
    appendLog('CONFIRM', '演示：模拟监护人点击确认链接')
  }

  const handleResend = async () => {
    setSubmitting(true)
    try {
      // 重发 = 重新提交：后端会重置 status=pending 并生成新 token
      await submitGuardianAuthorization(
        channel === 'email' ? { guardianEmail: email.trim() } : { guardianPhone: phone.trim() },
      )
      submittedThisSession.current = true
      setTip({ type: 'success', msg: '确认请求已重新发送。' })
      appendLog('RESEND')
    } catch (err) {
      setTip({ type: 'error', msg: `重新发送失败：${errMsg(err)}` })
      appendLog('RESEND_FAIL', errMsg(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = () => {
    setStatus('revoked')
    setTip({ type: 'success', msg: '已取消本次授权请求，状态重置为"未授权"。' })
    appendLog('CANCEL')
  }

  const handleRevoke = async () => {
    if (!window.confirm('确定撤销监护人授权吗？撤销后账号进入只读，AI 建议与复盘功能将暂停。')) return
    setSubmitting(true)
    try {
      await revokeGuardianAuthorization()
      setStatus('revoked')
      setTip({ type: 'success', msg: '授权已撤销，账号进入只读状态。' })
      appendLog('REVOKE')
    } catch (err) {
      setTip({ type: 'error', msg: `撤销失败：${errMsg(err)}` })
      appendLog('REVOKE_FAIL', errMsg(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleSwitchToExpired = () => {
    // 演示用：手动切换到 expired 状态，方便走查
    setStatus('expired')
    setTip({ type: 'error', msg: '演示模式：已切换到「已过期」状态。' })
    appendLog('EXPIRE', '演示模式手动触发')
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>监护人授权</h1>
        <p className={styles.subtitle}>
          为了使用 AI 建议 / 复盘功能，需要监护人确认（PRD 8.1 合规底线）。提交后，监护人将通过邮箱或短信收到一次性确认链接。
        </p>
      </header>

      <section className={styles.card}>
        <div className={styles.statusRow}>
          <span className={`${styles.statusTag} ${styles[`status_${info.tone}`]}`}>
            {loading ? '读取中' : info.title}
          </span>
          <p className={styles.statusText}>{loading ? '正在读取授权状态…' : info.text}</p>
          {status === 'active' && expiresAt && (
            <span className={styles.expire}>
              有效期至 {new Date(expiresAt).toLocaleDateString('zh-CN')}
            </span>
          )}
        </div>

        {tip && <p className={tip.type === 'success' ? styles.success : styles.error}>{tip.msg}</p>}

        {/* ───── 状态 1 / 4：未授权 & 已过期 → 提交表单 ───── */}
        {!loading && (status === 'revoked' || status === 'expired') && (
          <div className={styles.form}>
            <div className={styles.field}>
              <span className={styles.label}>联系方式（必填）</span>
              <div className={styles.channelTabs} role="tablist" aria-label="发送通道">
                <button
                  type="button"
                  role="tab"
                  aria-selected={channel === 'email'}
                  className={`${styles.channelTab} ${channel === 'email' ? styles.channelTabActive : ''}`}
                  onClick={() => setChannel('email')}
                >
                  邮箱
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={channel === 'phone'}
                  className={`${styles.channelTab} ${channel === 'phone' ? styles.channelTabActive : ''}`}
                  onClick={() => setChannel('phone')}
                >
                  手机短信
                </button>
              </div>
              <p className={styles.hint}>{channelHint}</p>
            </div>

            {channel === 'email' ? (
              <label className={styles.field}>
                <span className={styles.label}>监护人邮箱</span>
                <input
                  className={styles.textInput}
                  value={email}
                  placeholder="guardian@example.com"
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            ) : (
              <label className={styles.field}>
                <span className={styles.label}>监护人手机号</span>
                <input
                  className={styles.textInput}
                  value={phone}
                  placeholder="13800138000"
                  onChange={(e) => setPhone(e.target.value)}
                />
              </label>
            )}

            <label className={styles.agreeRow}>
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                aria-label="同意监护人授权协议"
              />
              <span>我已阅读并同意《监护人授权协议》《未成年人个人信息保护声明》</span>
            </label>

            {fieldErr && <p className={styles.error}>{fieldErr}</p>}

            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.submitBtn}
                disabled={submitting}
                onClick={handleSubmit}
              >
                {submitting ? '提交中…' : '发送确认请求'}
              </button>
              {status === 'expired' && (
                <button type="button" className={styles.linkBtn} onClick={handleSwitchToExpired}>
                  演示：切回「已过期」
                </button>
              )}
            </div>
          </div>
        )}

        {/* ───── 状态 2：等待确认 → 重发 / 取消 / 演示确认 ───── */}
        {!loading && status === 'pending' && (
          <div className={styles.form}>
            <div className={styles.codeBox}>
              <span className={styles.codeLabel}>本次确认请求</span>
              <ul className={styles.codeList}>
                <li>
                  <span className={styles.codeKey}>通道</span>
                  <span className={styles.codeVal}>{channel === 'email' ? '邮件' : '短信'}</span>
                </li>
                <li>
                  <span className={styles.codeKey}>目标</span>
                  <span className={styles.codeVal}>{channel === 'email' ? email : phone || '（未填写）'}</span>
                </li>
                <li>
                  <span className={styles.codeKey}>链接有效期</span>
                  <span className={styles.codeVal}>{channel === 'email' ? '24 小时' : '10 分钟'}</span>
                </li>
              </ul>
            </div>

            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.secondaryBtn}
                disabled={submitting}
                onClick={handleResend}
              >
                {submitting ? '发送中…' : '重新发送'}
              </button>
              <button type="button" className={styles.linkBtn} onClick={handleCancel}>
                取消请求
              </button>
              <button type="button" className={styles.linkBtn} onClick={handleSimulateConfirm}>
                演示：监护人点链接确认
              </button>
            </div>
          </div>
        )}

        {/* ───── 状态 3：已授权 → 撤销 / 演示到期 ───── */}
        {!loading && status === 'active' && (
          <div className={styles.form}>
            <div className={styles.codeBox}>
              <span className={styles.codeLabel}>授权信息</span>
              <ul className={styles.codeList}>
                <li>
                  <span className={styles.codeKey}>监护人</span>
                  <span className={styles.codeVal}>{email || phone || '（演示数据）'}</span>
                </li>
                <li>
                  <span className={styles.codeKey}>授权时间</span>
                  <span className={styles.codeVal}>{new Date().toLocaleString('zh-CN')}</span>
                </li>
                <li>
                  <span className={styles.codeKey}>到期时间</span>
                  <span className={styles.codeVal}>
                    {expiresAt ? new Date(expiresAt).toLocaleString('zh-CN') : '—'}
                  </span>
                </li>
              </ul>
            </div>

            <div className={styles.btnRow}>
              <button
                type="button"
                className={styles.dangerBtn}
                disabled={submitting}
                onClick={handleRevoke}
              >
                {submitting ? '处理中…' : '撤销授权'}
              </button>
              <button type="button" className={styles.linkBtn} onClick={handleSwitchToExpired}>
                演示：触发到期
              </button>
            </div>
          </div>
        )}
      </section>

      {/* 操作日志 */}
      <section className={styles.logCard}>
        <h2 className={styles.logTitle}>操作日志</h2>
        {logs.length === 0 ? (
          <p className={styles.logEmpty}>暂无操作</p>
        ) : (
          <ul className={styles.logList}>
            {logs.map((log, idx) => (
              <li key={idx} className={styles.logItem}>
                <span className={styles.logAt}>{log.at}</span>
                <span className={styles.logAction}>{log.action}</span>
                {log.detail && <span className={styles.logDetail}>{log.detail}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

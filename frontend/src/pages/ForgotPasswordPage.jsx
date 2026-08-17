import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import FormField from '../components/FormField.jsx'
import { MailIcon, LockIcon, ShieldIcon, CheckIcon } from '../components/Icons.jsx'
import { useCodeCountdown } from '../hooks/useCodeCountdown.js'
import {
  validateEmail,
  validateCode,
  validatePasswordStrength,
  validateConfirmPassword
} from '../utils/validators.js'
import { sendResetCode, verifyResetCode, resetPassword } from '../services/authApi.js'

// step 1: 邮箱 + 验证码验证身份
// step 2: 设置新密码
export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)

  const [email, setEmail] = useState('')
  const [emailErr, setEmailErr] = useState('')

  const [code, setCode] = useState('')
  const [codeErr, setCodeErr] = useState('')
  const codeCD = useCodeCountdown()

  const [newPwd, setNewPwd] = useState('')
  const [newPwdErr, setNewPwdErr] = useState('')

  const [confirmPwd, setConfirmPwd] = useState('')
  const [confirmPwdErr, setConfirmPwdErr] = useState('')

  const [tip, setTip] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  /* ---------- Step 1: 发送验证码 ---------- */
  async function handleSendCode() {
    const err = validateEmail(email)
    setEmailErr(err)
    if (err) return
    try {
      await sendResetCode(email)
      codeCD.start(60)
      setTip({ type: 'success', msg: '验证码已发送至邮箱，请注意查收' })
    } catch (e) {
      setTip({ type: 'error', msg: e.message || '发送失败' })
    }
  }

  /* ---------- Step 1: 验证 → 进入 step 2 ---------- */
  async function handleStep1Next(e) {
    e.preventDefault()
    setTip(null)
    const eErr = validateEmail(email)
    const cErr = validateCode(code)
    setEmailErr(eErr)
    setCodeErr(cErr)
    if (eErr || cErr) return

    setSubmitting(true)
    try {
      // 验证邮箱验证码（生产环境可改为签发短期 token 带到下一步）
      await verifyResetCode(email, code)
      setStep(2)
      setTip(null)
    } catch (e) {
      setTip({ type: 'error', msg: e.message || '验证失败' })
    } finally {
      setSubmitting(false)
    }
  }

  /* ---------- Step 2: 提交新密码 ---------- */
  async function handleReset(e) {
    e.preventDefault()
    setTip(null)

    const pErr = validatePasswordStrength(newPwd)
    const cpErr = validateConfirmPassword(newPwd, confirmPwd)
    setNewPwdErr(pErr)
    setConfirmPwdErr(cpErr)
    if (pErr || cpErr) return

    setSubmitting(true)
    try {
      await resetPassword({
        email,
        code,
        newPassword: newPwd,
        confirmPassword: confirmPwd
      })
      setTip({ type: 'success', msg: '密码已重置，即将返回登录页…' })
      setTimeout(() => navigate('/login'), 900)
    } catch (e) {
      setTip({ type: 'error', msg: e.message || '重置失败' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="page-bg-decor" />
      <div className="auth-card">
        <div className="auth-header">
          <img className="auth-logo-img" src="/brand/logo-full-black.png" alt="EpochX" />
          <p className="auth-subtitle">
            {step === 1 ? '我们会向你的邮箱发送验证码' : '请设置一个新的登录密码'}
          </p>
        </div>

        {/* 步骤指示器 */}
        <div className="step-indicator">
          <div className={`step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'done' : ''}`}>
            {step > 1 ? <CheckIcon style={{ width: 14, height: 14 }} /> : '1'}
          </div>
          <div className={`line ${step > 1 ? 'done' : ''}`} />
          <div className={`step ${step >= 2 ? 'active' : ''}`}>2</div>
        </div>

        {tip && <div className={`form-tip ${tip.type}`}>{tip.msg}</div>}

        {step === 1 ? (
          <form onSubmit={handleStep1Next} noValidate>
            <FormField
              label="注册邮箱"
              required
              icon={<MailIcon />}
              type="email"
              placeholder="请输入注册时使用的邮箱"
              value={email}
              onChange={(v) => { setEmail(v); setEmailErr('') }}
              onBlur={() => setEmailErr(validateEmail(email))}
              error={emailErr}
              autoComplete="email"
            />

            <FormField
              label="邮箱验证码"
              required
              icon={<ShieldIcon />}
              placeholder="请输入 6 位验证码"
              value={code}
              onChange={(v) => { setCode(v.replace(/\D/g, '')); setCodeErr('') }}
              onBlur={() => setCodeErr(validateCode(code))}
              error={codeErr}
              maxLength={6}
              suffix={codeCD.text}
              suffixDisabled={codeCD.sending || !!emailErr}
              onSuffixClick={handleSendCode}
              autoComplete="one-time-code"
            />

            <button type="submit" className="btn-primary" style={{ marginTop: 6 }} disabled={submitting}>
              {submitting ? '验证中…' : '下一步'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleReset} noValidate>
            <FormField
              label="新密码"
              required
              icon={<LockIcon />}
              type="password"
              placeholder="6-32 位，建议字母与数字组合"
              value={newPwd}
              onChange={(v) => {
                setNewPwd(v)
                setNewPwdErr('')
                if (confirmPwd) setConfirmPwdErr(validateConfirmPassword(v, confirmPwd))
              }}
              onBlur={() => setNewPwdErr(validatePasswordStrength(newPwd))}
              error={newPwdErr}
              autoComplete="new-password"
            />

            <FormField
              label="确认新密码"
              required
              icon={<CheckIcon />}
              type="password"
              placeholder="请再次输入新密码"
              value={confirmPwd}
              onChange={(v) => { setConfirmPwd(v); setConfirmPwdErr('') }}
              onBlur={() => setConfirmPwdErr(validateConfirmPassword(newPwd, confirmPwd))}
              error={confirmPwdErr}
              autoComplete="new-password"
            />

            <button type="submit" className="btn-primary" style={{ marginTop: 6 }} disabled={submitting}>
              {submitting ? '提交中…' : '确认重置'}
            </button>
          </form>
        )}

        <div className="auth-footer">
          <Link className="link" to="/login">返回登录</Link>
          <span className="sep">·</span>
          <Link className="link" to="/register">注册新账号</Link>
        </div>
      </div>
    </div>
  )
}

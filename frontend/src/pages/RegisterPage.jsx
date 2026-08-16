import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import FormField from '../components/FormField.jsx'
import { LogoIcon, MailIcon, LockIcon, ShieldIcon, CheckIcon } from '../components/Icons.jsx'
import { useCodeCountdown } from '../hooks/useCodeCountdown.js'
import {
  validateEmail,
  validateCode,
  validatePasswordStrength,
  validateConfirmPassword
} from '../utils/validators.js'
import { sendRegisterCode, register } from '../services/authApi.js'

export default function RegisterPage() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [emailErr, setEmailErr] = useState('')

  const [code, setCode] = useState('')
  const [codeErr, setCodeErr] = useState('')
  const codeCD = useCodeCountdown()

  const [password, setPassword] = useState('')
  const [passwordErr, setPasswordErr] = useState('')

  const [confirmPwd, setConfirmPwd] = useState('')
  const [confirmPwdErr, setConfirmPwdErr] = useState('')

  const [tip, setTip] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  /* ---------- 发送验证码 ---------- */
  async function handleSendCode() {
    const err = validateEmail(email)
    setEmailErr(err)
    if (err) return
    try {
      await sendRegisterCode(email)
      codeCD.start(60)
      setTip({ type: 'success', msg: '验证码已发送至邮箱，请注意查收' })
    } catch (e) {
      setTip({ type: 'error', msg: e.message || '发送失败' })
    }
  }

  /* ---------- 提交 ---------- */
  async function handleSubmit(e) {
    e.preventDefault()
    setTip(null)

    const eErr = validateEmail(email)
    const cErr = validateCode(code)
    const pErr = validatePasswordStrength(password)
    const cpErr = validateConfirmPassword(password, confirmPwd)

    setEmailErr(eErr)
    setCodeErr(cErr)
    setPasswordErr(pErr)
    setConfirmPwdErr(cpErr)

    if (eErr || cErr || pErr || cpErr) return

    setSubmitting(true)
    try {
      await register({ email, code, password, confirmPassword: confirmPwd })
      setTip({ type: 'success', msg: '注册成功，即将跳转登录页…' })
      setTimeout(() => navigate('/login'), 900)
    } catch (e) {
      setTip({ type: 'error', msg: e.message || '注册失败' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="page-bg-decor" />
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo"><LogoIcon /></div>
          <h1 className="auth-title">创建你的账号</h1>
          <p className="auth-subtitle">让我们一起记录学习的点滴</p>
        </div>

        {tip && <div className={`form-tip ${tip.type}`}>{tip.msg}</div>}

        <form onSubmit={handleSubmit} noValidate>
          <FormField
            label="邮箱"
            required
            icon={<MailIcon />}
            type="email"
            placeholder="请输入常用邮箱，用于接收验证码"
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

          <FormField
            label="设置密码"
            required
            icon={<LockIcon />}
            type="password"
            placeholder="6-32 位，建议字母与数字组合"
            value={password}
            onChange={(v) => {
              setPassword(v)
              setPasswordErr('')
              if (confirmPwd) setConfirmPwdErr(validateConfirmPassword(v, confirmPwd))
            }}
            onBlur={() => setPasswordErr(validatePasswordStrength(password))}
            error={passwordErr}
            autoComplete="new-password"
          />

          <FormField
            label="确认密码"
            required
            icon={<CheckIcon />}
            type="password"
            placeholder="请再次输入密码"
            value={confirmPwd}
            onChange={(v) => { setConfirmPwd(v); setConfirmPwdErr('') }}
            onBlur={() => setConfirmPwdErr(validateConfirmPassword(password, confirmPwd))}
            error={confirmPwdErr}
            autoComplete="new-password"
          />

          <button type="submit" className="btn-primary" style={{ marginTop: 6 }} disabled={submitting}>
            {submitting ? '注册中…' : '创建账号'}
          </button>
        </form>

        <div className="auth-footer">
          已有账号？
          <Link className="link" to="/login">返回登录</Link>
        </div>
      </div>
    </div>
  )
}

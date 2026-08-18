import React, { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { isNetworkError } from '../services/http'
import { cacheGet, cacheSet } from '../services/localFallback'
import FormField from '../components/FormField.jsx'
import { MailIcon, LockIcon, ShieldIcon } from '../components/Icons.jsx'
import { useCodeCountdown } from '../hooks/useCodeCountdown.js'
import { validateEmail, validateCode, validatePassword } from '../utils/validators.js'
import { useAuth } from '../context/AuthContext.jsx'
import {
  sendLoginCode,
  loginByEmailCode,
  loginByPassword
} from '../services/authApi.js'

// loginMode: 'code' 邮箱验证码登录（默认） | 'password' 密码登录
export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { refresh } = useAuth()
  const [mode, setMode] = useState('code')

  // 公共字段
  const [email, setEmail] = useState('')
  const [emailErr, setEmailErr] = useState('')

  // 验证码模式
  const [code, setCode] = useState('')
  const [codeErr, setCodeErr] = useState('')
  const codeCD = useCodeCountdown()

  // 密码模式
  const [password, setPassword] = useState('')
  const [passwordErr, setPasswordErr] = useState('')

  const [tip, setTip] = useState(null) // { type: 'success'|'error', msg }
  const [submitting, setSubmitting] = useState(false)

  // 仅做界面回填，绝不伪造登录态或自动跳转
  useEffect(() => {
    const cachedEmail = cacheGet('login:lastEmail')
    if (cachedEmail && !email) {
      setEmail(cachedEmail)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 持久化最近一次邮箱，便于下次回填
  useEffect(() => {
    if (email) cacheSet('login:lastEmail', email)
  }, [email])

  /* ---------- 发送验证码 ---------- */
  async function handleSendCode() {
    const err = validateEmail(email)
    setEmailErr(err)
    if (err) return
    cacheSet('login:lastEmail', email)
    try {
      await sendLoginCode(email)
      codeCD.start(60)
      setTip({ type: 'success', msg: '验证码已发送，请注意查收邮箱' })
    } catch (e) {
      if (e.code === 'EMAIL_NOT_REGISTERED') {
        setEmailErr('该邮箱尚未注册')
        setTip({ type: 'error', msg: '该邮箱尚未注册，请先注册' })
      } else if (isNetworkError(e)) {
        setTip({ type: 'error', msg: '服务暂不可用，请稍后再试' })
      } else {
        setTip({ type: 'error', msg: e.message || '发送失败' })
      }
    }
  }

  /* ---------- 提交 ---------- */
  async function handleSubmit(e) {
    e && e.preventDefault()
    setTip(null)

    const eErr = validateEmail(email)
    setEmailErr(eErr)

    if (mode === 'code') {
      const cErr = validateCode(code)
      setCodeErr(cErr)
      if (eErr || cErr) return
    } else {
      const pErr = validatePassword(password)
      setPasswordErr(pErr)
      if (eErr || pErr) return
    }

    setSubmitting(true)
    try {
      if (mode === 'code') {
        await loginByEmailCode(email, code)
      } else {
        await loginByPassword(email, password)
      }
      cacheSet('login:lastEmail', email)
      setTip({ type: 'success', msg: '登录成功，即将进入首页…' })
      // 登录接口只签发 session cookie，不会更新 AuthContext 里缓存的登录态，
      // 不先 refresh() 就跳转会被 RequireAuth 当成未登录弹回登录页。
      // from 是 RequireAuth 重定向时带过来的原目标路径，没有则回默认落地页。
      await refresh()
      const from = location.state?.from?.pathname ?? '/study-guide'
      setTimeout(() => navigate(from, { replace: true }), 800)
    } catch (e) {
      setTip({ type: 'error', msg: isNetworkError(e) ? '服务暂不可用，请稍后再试' : (e.message || '登录失败') })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="page-bg-decor" />
      <div className="auth-card auth-card--split">
        <div className="auth-split-media">
          <video src="/promo.mp4" autoPlay muted loop playsInline />
        </div>

        <div className="auth-split-form">
          {/* Tab 切换：邮箱验证码登录 / 密码登录 */}
          <div className="auth-tabs" role="tablist">
            <button
              role="tab"
              className={`auth-tab ${mode === 'code' ? 'active' : ''}`}
              onClick={() => { setMode('code'); setTip(null) }}
              aria-selected={mode === 'code'}
            >
              邮箱登录
            </button>
            <button
              role="tab"
              className={`auth-tab ${mode === 'password' ? 'active' : ''}`}
              onClick={() => { setMode('password'); setTip(null) }}
              aria-selected={mode === 'password'}
            >
              密码登录
            </button>
          </div>

          {tip && <div className={`form-tip ${tip.type}`}>{tip.msg}</div>}

          <form onSubmit={handleSubmit} noValidate>
            <FormField
              label="邮箱"
              required
              icon={<MailIcon />}
              type="email"
              placeholder="请输入注册邮箱"
              value={email}
              onChange={(v) => { setEmail(v); setEmailErr('') }}
              onBlur={() => setEmailErr(validateEmail(email))}
              error={emailErr}
              autoComplete="email"
            />

            {mode === 'code' ? (
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
                suffix={codeCD.sending ? <span className="spinner spinner--sm" aria-hidden="true" /> : codeCD.text}
                suffixDisabled={codeCD.sending || !!emailErr}
                onSuffixClick={handleSendCode}
                autoComplete="one-time-code"
              />
            ) : (
              <FormField
                label="密码"
                required
                icon={<LockIcon />}
                type="password"
                placeholder="请输入登录密码"
                value={password}
                onChange={(v) => { setPassword(v); setPasswordErr('') }}
                onBlur={() => setPasswordErr(validatePassword(password))}
                error={passwordErr}
                autoComplete="current-password"
              />
            )}

            {mode === 'password' && (
              <div className="form-helper-row">
                <span />
                <Link className="link" to="/forgot-password">忘记密码？</Link>
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting && <span className="spinner spinner--sm" aria-hidden="true" />}
              {submitting ? '登录中…' : '登 录'}
            </button>
          </form>

          <div className="auth-footer">
            还没有账号？
            <Link className="link" to="/register">立即注册</Link>
          </div>
        </div>
      </div>
    </div>
  )
}

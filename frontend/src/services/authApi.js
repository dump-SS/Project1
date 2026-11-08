// 接口请求封装 —— 遵循 docs/api-design-unified.md 约定：
// 1. 基础路径默认 /api/v1；分域部署时读 VITE_API_BASE_URL
//    （口径必须与 services/http.ts 的 BASE_URL 保持一致，改一处记得改另一处）
// 2. 登录态通过 HttpOnly Session Cookie 维持，浏览器自动携带
// 3. 统一错误格式 { error: { code, message, field } }
// 4. 字段命名 camelCase
//
// ⚠️ 不要把 VITE_API_BASE_URL 留成空字符串：`??` 只在 null/undefined 时兜底，
//    空串会丢掉 /api/v1 前缀且不报错（见 frontend/.env.example）。

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json' }

  const res = await fetch(BASE + path, {
    ...options,
    credentials: 'include', // 携带并保存 HttpOnly Session Cookie
    headers: { ...headers, ...(options.headers || {}) },
    body: options.body ? JSON.stringify(options.body) : undefined
  })

  let data = null
  try { data = await res.json() } catch (_) {}

  if (!res.ok) {
    // 统一错误格式：{ error: { code, message, field } }
    const code = (data && data.error && data.error.code) || 'INTERNAL_ERROR'
    const message = (data && data.error && data.error.message) || '请求失败，请稍后再试'
    const field = (data && data.error && data.error.field) || undefined
    const e = new Error(message)
    e.code = code
    e.field = field
    e.status = res.status
    throw e
  }
  return data
}

/* ===================== 验证码发送 ===================== */

// 发送注册邮箱验证码
export function sendRegisterCode(email) {
  return request('/auth/send-register-code', {
    method: 'POST',
    body: { email }
  })
}

// 发送重置密码邮箱验证码
export function sendResetCode(email) {
  return request('/auth/send-reset-code', {
    method: 'POST',
    body: { email }
  })
}

// 发送登录邮箱验证码
export function sendLoginCode(email) {
  return request('/auth/send-login-code', {
    method: 'POST',
    body: { email }
  })
}

/* ===================== 注册 ===================== */

export function register(payload) {
  // payload: { email, code, password, confirmPassword }
  // 注册成功不自动登录，跳转登录页后由登录接口签发 Session
  return request('/auth/register', {
    method: 'POST',
    body: payload
  })
}

/* ===================== 登录 ===================== */

// 邮箱 + 验证码登录（成功后服务端通过 Set-Cookie 下发 Session）
export function loginByEmailCode(email, code) {
  return request('/auth/login-email-code', {
    method: 'POST',
    body: { email, code }
  })
}

// 邮箱 + 密码登录
export function loginByPassword(email, password) {
  return request('/auth/login-password', {
    method: 'POST',
    body: { email, password }
  })
}

/* ===================== 登录态 ===================== */

// 获取当前登录用户（用于校验登录态）
export function getCurrentUser() {
  return request('/auth/me')
}

// 退出登录
export function logout() {
  return request('/auth/logout', { method: 'POST' })
}

/* ===================== 重置密码 ===================== */

// 验证邮箱验证码（重置密码流程用）
export function verifyResetCode(email, code) {
  return request('/auth/verify-reset-code', {
    method: 'POST',
    body: { email, code }
  })
}

// 设置新密码
export function resetPassword(payload) {
  // payload: { email, code, newPassword, confirmPassword }
  return request('/auth/reset-password', {
    method: 'POST',
    body: payload
  })
}
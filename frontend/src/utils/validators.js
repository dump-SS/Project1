// 通用表单校验工具

export const EMAIL_REGEX = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

export function validateEmail(email) {
  if (!email) return '请输入邮箱'
  if (!EMAIL_REGEX.test(email)) return '邮箱格式不正确'
  return ''
}

export function validatePassword(pwd) {
  if (!pwd) return '请输入密码'
  if (pwd.length < 6) return '密码至少 6 位'
  if (pwd.length > 32) return '密码最长 32 位'
  return ''
}

// 密码复杂度：大写字母 / 小写字母 / 数字 / 符号 四类中至少满足两类
export function validatePasswordStrength(pwd) {
  const base = validatePassword(pwd)
  if (base) return base
  const kinds = [/[A-Z]/, /[a-z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(pwd)).length
  if (kinds < 2) return '密码需包含大写字母、小写字母、数字、符号中的至少两种'
  return ''
}

export function validateConfirmPassword(pwd, confirm) {
  if (!confirm) return '请再次输入密码'
  if (pwd !== confirm) return '两次输入的密码不一致'
  return ''
}

export function validateCode(code) {
  if (!code) return '请输入验证码'
  if (!/^\d{6}$/.test(code)) return '验证码为 6 位数字'
  return ''
}

export function classNames(...args) {
  return args.filter(Boolean).join(' ')
}

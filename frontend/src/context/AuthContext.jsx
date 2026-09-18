// 全局登录态。挂载时调用一次 GET /auth/me 校验 session（HttpOnly cookie，
// 浏览器自动携带，见 authApi.js 顶部注释），暴露给 RequireAuth 做路由守卫、
// 给 AppShell 显示当前用户邮箱和退出登录。
//
// 只做「校验登录态是否存在」，不做用户资料的增删改——那是各业务页面自己的事。

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getCurrentUser, logout as logoutRequest } from '../services/authApi.js'
import { AUTH_EXPIRED_EVENT } from '../services/http'

const AuthContext = createContext(null)

// 'checking'：正在校验（避免守卫在结果出来前误判为未登录）
// 'authenticated' / 'anonymous'：校验结果
export function AuthProvider({ children }) {
  const [status, setStatus] = useState('checking')
  const [user, setUser] = useState(null)

  const refresh = useCallback(async () => {
    setStatus('checking')
    try {
      const data = await getCurrentUser()
      setUser(data?.user ?? null)
      setStatus('authenticated')
    } catch {
      // /auth/me 401 时 authApi 的 request() 会 throw，这里统一按未登录处理，
      // 不区分具体错误码——校验登录态不需要向用户展示这层细节
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // 会话在页面停留期间过期时，业务接口会返回 401 UNAUTHENTICATED，
  // http.ts 的 throwIfNotOk 随即广播该事件。这里把登录态置回 anonymous，
  // RequireAuth 会立刻弹回 /login 并记下当前路径，登录后自动跳回原页面。
  //
  // 注意：/auth/me 的 401 UNAUTHORIZED 与登录密码错误的 PASSWORD_INCORRECT
  // 不会触发该事件（见 http.ts 的 throwIfNotOk），否则登录失败会被反复弹回。
  useEffect(() => {
    const onAuthExpired = () => {
      setUser(null)
      setStatus('anonymous')
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired)
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      // 无论后端是否成功都清本地状态：cookie 可能已经失效，
      // 留在「已登录」状态会让用户卡在需要鉴权的页面里出不去
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  const value = useMemo(() => ({ status, user, refresh, logout }), [status, user, refresh, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth 必须在 <AuthProvider> 内部使用')
  }
  return ctx
}

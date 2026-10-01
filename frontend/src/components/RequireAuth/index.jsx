// 路由守卫：未登录访问业务页面时弹回登录页，并记下原目标路径，
// 登录成功后 LoginPage 会把用户带回来（而不是固定跳去 /study-guide）。
//
// `allowGuest`（D1/D43）：游客态允许进入**指定的**非 AI 页面（计划 / 计时），
// 其余页面仍是「必须登录」。这里只叠加一层判断，**不动 401 事件机制**
// （http.ts 广播 → AuthContext 置 anonymous → 本组件弹回登录）。
//
// status === 'checking' 时不下结论——AuthContext 挂载后会先发一次 /auth/me 请求，
// 结果出来前如果直接当作「未登录」处理，刷新页面时会先闪一下登录页再跳回来。

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'

export default function RequireAuth({ allowGuest = false }) {
  const { status, isGuest } = useAuth()
  const location = useLocation()

  if (status === 'checking') {
    // 校验通常在一次本地请求的时间内完成，这里只做最基础的占位，
    // 不引入额外的 loading 组件规范
    return null
  }

  if (status === 'anonymous') {
    if (allowGuest && isGuest) return <Outlet />
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

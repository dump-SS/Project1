// 路由守卫：未登录访问业务页面时弹回登录页，并记下原目标路径，
// 登录成功后 LoginPage 会把用户带回来（而不是固定跳去 /study-guide）。
//
// status === 'checking' 时不下结论——AuthContext 挂载后会先发一次 /auth/me 请求，
// 结果出来前如果直接当作「未登录」处理，刷新页面时会先闪一下登录页再跳回来。

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'

export default function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'checking') {
    // 校验通常在一次本地请求的时间内完成，这里只做最基础的占位，
    // 不引入额外的 loading 组件规范
    return null
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

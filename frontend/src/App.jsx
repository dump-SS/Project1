import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
// 个人数据页用 TypeScript 编写。Vite 的 React 插件支持 .jsx 与 .tsx 共存，
// 两边都不必为对方改写，import 时写明扩展名即可。
import PersonalDataPage from './pages/PersonalData/index.tsx'

export default function App() {
  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        {/* TODO: 登录态校验待接入 —— 该路由目前可直接访问，
            等 mock-server 的会话校验对接好后再包一层路由守卫 */}
        <Route path="/personal-data" element={<PersonalDataPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </div>
  )
}

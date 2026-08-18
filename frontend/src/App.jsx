import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import RequireAuth from './components/RequireAuth/index.jsx'
import AppShell from './components/AppShell/index.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
// 个人数据页用 TypeScript 编写。Vite 的 React 插件支持 .jsx 与 .tsx 共存，
// 两边都不必为对方改写，import 时写明扩展名即可。
import PersonalDataPage from './pages/PersonalData/index.tsx'
import StudyTimerPage from './pages/StudyTimer/index.jsx'
import StudyPlanEditor from './pages/StudyPlanEditor/index.jsx'
import StudyGuide from './pages/StudyGuide/index.jsx'
import SettingsPage from './pages/Settings/index.jsx'
import SummaryReviewPage from './pages/SummaryReview/index.tsx'
import Goals from './pages/Goals/index.jsx'
import RecommendationsPage from './pages/Recommendations/index.tsx'
import ProfileSetupPage from './pages/ProfileSetup/index.tsx'
import GuardianAuthPage from './pages/GuardianAuth/index.tsx'

export default function App() {
  return (
    <div className="app-shell">
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />

          {/* 以下四条业务路由收在 RequireAuth 之下：未登录访问会被弹回 /login，
              登录成功后会带回原本想去的地址（见 RequireAuth 与 LoginPage）。
              AppShell 是四条路由共用的顶部导航条，登录/注册/找回密码页不套它。 */}
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<Navigate to="/study-guide" replace />} />
              <Route path="/personal-data" element={<PersonalDataPage />} />
              <Route path="/study-timer" element={<StudyTimerPage />} />
              <Route path="/study-plan" element={<StudyPlanEditor />} />
              <Route path="/study-guide" element={<StudyGuide />} />
              <Route path="/goals" element={<Goals />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/summary-review" element={<SummaryReviewPage />} />
              <Route path="/recommendations" element={<RecommendationsPage />} />
              <Route path="/profile-setup" element={<ProfileSetupPage />} />
              <Route path="/guardian-auth" element={<GuardianAuthPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </div>
  )
}
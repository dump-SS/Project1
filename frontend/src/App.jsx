import React, { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import RequireAuth from './components/RequireAuth/index.jsx'
import AppShell from './components/AppShell/index.jsx'
import LaunchScreen from './components/LaunchScreen/index.jsx'
import CustomCursor from './components/CustomCursor/index.jsx'
import CloudTransition from './components/CloudTransition/index.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
// 个人数据页用 TypeScript 编写。Vite 的 React 插件支持 .jsx 与 .tsx 共存，
// 两边都不必为对方改写，import 时写明扩展名即可。
import PersonalDataPage from './pages/PersonalData/index.tsx'
import StudyTimerPage from './pages/StudyTimer/index.jsx'
import StudyGuide from './pages/StudyGuide/index.jsx'
import SettingsPage from './pages/Settings/index.jsx'
import SummaryReviewPage from './pages/SummaryReview/index.tsx'
import Goals from './pages/Goals/index.jsx'
import RecommendationsPage from './pages/Recommendations/index.tsx'
import ProfileSetupPage from './pages/ProfileSetup/index.tsx'
import GuardianAuthPage from './pages/GuardianAuth/index.tsx'
import CommunityDemoBadge from './components/CommunityDemoBadge/index.jsx'
import KnowledgePage from './pages/Knowledge/index.tsx'
import ErrorBookPage from './pages/ErrorBook/index.tsx'
import ChatPage from './pages/Chat/index.tsx'
import CommunityUploadPage from './pages/Community/Upload.tsx'
import CommunityComparePage from './pages/Community/Compare.tsx'

// 官网落地页：路由级代码分割（dev-spec §2.3），不套 AppShell / RequireAuth。
const LandingPage = lazy(() => import('./pages/Landing/index.tsx'))

export default function App() {
  const location = useLocation()
  // 落地页跳过全局开屏动画与自定义光标（旧液态玻璃语言 + 光标会干扰手电视效），
  // CloudTransition 只在主题切换时触发，落地页无切换入口，自然不出现。
  const isLanding = location.pathname === '/'

  return (
    <div className="app-shell">
      <ThemeProvider>
        <AuthProvider>
          {!isLanding && <LaunchScreen />}
          {!isLanding && <CustomCursor />}
          <CloudTransition />
          <Routes>
          <Route
            path="/"
            element={
              <Suspense fallback={<div style={{ position: 'fixed', inset: 0, background: '#10161E' }} />}>
                <LandingPage />
              </Suspense>
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />

          {/* 业务路由分两层（D1/D43 游客态只**叠加**守卫，不重写 401 机制）：
              · 外层 RequireAuth allowGuest：登录用户与游客都可进；
                但只有「非 AI 核心闭环」的导学 / 计时两页对游客真正开放（见各页自身），
                其余页面在内层仍要求登录，AI 入口由 AppShell 对游客标灰。
              · 内层 RequireAuth：其余业务页必须登录。
              登录成功后会带回原本想去的地址（见 RequireAuth 与 LoginPage）。 */}
          <Route element={<RequireAuth allowGuest />}>
            <Route element={<AppShell />}>
              {/* 游客可试用（非 AI 功能）：计划为规则引擎、计时为本地计时不落库 */}
              <Route path="/study-guide" element={<StudyGuide />} />
              <Route path="/study-plan" element={<Navigate to="/study-guide" replace />} />
              <Route path="/study-timer" element={<StudyTimerPage />} />

              {/* 其余业务页：必须登录 */}
              <Route element={<RequireAuth />}>
                <Route path="/personal-data" element={<PersonalDataPage />} />
                <Route path="/goals" element={<Goals />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/summary-review" element={<SummaryReviewPage />} />
                <Route path="/recommendations" element={<RecommendationsPage />} />
                <Route path="/profile-setup" element={<ProfileSetupPage />} />
                <Route path="/guardian-auth" element={<GuardianAuthPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/error-book" element={<ErrorBookPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/community" element={<Navigate to="/community/upload" replace />} />
                <Route
                  path="/community/upload"
                  element={
                    <CommunityDemoBadge><CommunityUploadPage /></CommunityDemoBadge>
                  }
                />
                <Route
                  path="/community/compare"
                  element={
                    <CommunityDemoBadge><CommunityComparePage /></CommunityDemoBadge>
                  }
                />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </div>
  )
}
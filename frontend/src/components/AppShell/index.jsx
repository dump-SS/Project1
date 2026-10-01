/**
 * 业务页共用外壳:左侧边栏导航(桌面,支持折叠)+ 底部 Tab(移动端)。
 *
 * v0.4 信息架构重构:从顶栏改为左侧边栏。
 * - 桌面:左侧固定边栏,展开 240px(图标+文字)/ 折叠 64px(仅图标)。
 *   折叠按钮在边栏底部。主题切换、用户邮箱、退出按钮也在底部。
 * - 移动:底部固定 6 Tab + "我的"抽屉(不变)。
 *
 * 游客态(D1/D43,2026-09-30 增补):
 * - 身份区显示「游客 ?」,点开即登录/注册入口(常驻,任何页面都能转登录,不弹确认);
 * - 除「导学 / 计时」两页外的导航项对游客**标灰**(AI 能力与用户数据页都需要登录),
 *   点击不跳转、改为展开登录入口。
 *
 * 折叠状态持久化到 localStorage(key: epochx-sidebar-collapsed)。
 * 路由路径与页面本身不变,仅调整导航呈现结构。
 */

import { useState, useEffect } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useTheme } from '../../context/ThemeContext.jsx'
import PageTransition from '../PageTransition/index.jsx'
import styles from './index.module.css'

// SVG 图标库 · 24x24 viewBox · currentColor 跟随主题色
const Icon = ({ name, size = 18 }) => {
  const props = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    xmlns: 'http://www.w3.org/2000/svg',
    'aria-hidden': 'true',
  }
  switch (name) {
    case 'study':
      // 导学 · 书 + 高亮线
      return (
        <svg {...props}>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          <path d="M9 7h6M9 11h4" />
        </svg>
      )
    case 'timer':
      // 计时 · 时钟
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
          <path d="M9 2h6" />
        </svg>
      )
    case 'data':
      // 数据 · 柱状图
      return (
        <svg {...props}>
          <path d="M3 3v18h18" />
          <rect x="7" y="12" width="3" height="6" />
          <rect x="12" y="8" width="3" height="10" />
          <rect x="17" y="14" width="3" height="4" />
        </svg>
      )
    case 'review':
      // 复盘 · 笔记本 + 对勾
      return (
        <svg {...props}>
          <path d="M4 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4z" />
          <path d="M8 2v4M16 2v4M4 10h16" />
          <path d="M9 15l2 2 4-4" />
        </svg>
      )
    case 'suggest':
      // 建议 · 灯泡
      return (
        <svg {...props}>
          <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.7.6 1 1.4 1 2.3v1h6v-1c0-.9.3-1.7 1-2.3A7 7 0 0 0 12 2z" />
        </svg>
      )
    case 'goal':
      // 目标 · 靶心同心圆
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="5" />
          <circle cx="12" cy="12" r="1.5" fill="currentColor" />
        </svg>
      )
    case 'settings':
      // 设置 · 齿轮
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      )
    case 'profile':
      // 资料建档 · 用户
      return (
        <svg {...props}>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21a8 8 0 0 1 16 0" />
        </svg>
      )
    case 'shield':
      // 监护人授权 · 盾牌 + 勾
      return (
        <svg {...props}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      )
    case 'logout':
      // 退出 · 箭头 + 门
      return (
        <svg {...props}>
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="M16 17l5-5-5-5M21 12H9" />
        </svg>
      )
    case 'chevronLeft':
      return (
        <svg {...props}>
          <path d="M15 18l-6-6 6-6" />
        </svg>
      )
    case 'chevronRight':
      return (
        <svg {...props}>
          <path d="M9 18l6-6-6-6" />
        </svg>
      )
    case 'knowledge':
      // 学科知识库 · 打开的书
      return (
        <svg {...props}>
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
        </svg>
      )
    case 'errorBook':
      // 错题本 · 带叉的文档
      return (
        <svg {...props}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M9 13l6 6M15 13l-6 6" />
        </svg>
      )
    case 'chat':
      // AI 辅导 · 对话气泡
      return (
        <svg {...props}>
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
          <path d="M8.5 10.5h7M8.5 13.5h4" />
        </svg>
      )
    case 'community':
      // 匿名群体对比 · 人群
      return (
        <svg {...props}>
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      )
    default:
      return null
  }
}

// 主导航:6 项高频业务页 + 学科组(板块二,origin/main 合并引入)
// guestBlocked: 游客态下不可用（AI 能力 / 用户数据页）——只有计划与计时对游客开放
// （D1「游客可试用非 AI 功能」；两页自身在游客态下走本地数据、不落库）
const PRIMARY_NAV = [
  { to: '/study-guide', label: '导学', icon: 'study' },
  { to: '/study-timer', label: '计时', icon: 'timer' },
  { to: '/personal-data', label: '数据', icon: 'data', guestBlocked: true },
  { to: '/summary-review', label: '复盘', icon: 'review', guestBlocked: true },
  { to: '/recommendations', label: '建议', icon: 'suggest', guestBlocked: true },
  { to: '/goals', label: '目标', icon: 'goal', guestBlocked: true },
  { to: '/knowledge', label: '学科', icon: 'knowledge', guestBlocked: true },
  { to: '/error-book', label: '错题', icon: 'errorBook', guestBlocked: true },
  { to: '/chat', label: 'AI辅导', icon: 'chat', guestBlocked: true },
  { to: '/community/upload', label: '群体', icon: 'community', guestBlocked: true },
]

// 「我的」下拉:2 个低频页。
// ⚠️ 「监护人授权」不再单列——D41 把它归位到「设置 → 授权与隐私」子页
// （另一处入口在激活式建档流程里，低龄门槛会强制走到）。旧路由 /guardian-auth 仍可直达。
const ME_NAV = [
  { to: '/settings', label: '设置', icon: 'settings' },
  { to: '/profile-setup', label: '资料建档', icon: 'profile' },
]

const STORAGE_KEY = 'epochx-sidebar-collapsed'

function isMeActive(pathname) {
  return ME_NAV.some((it) => pathname.startsWith(it.to))
}

export default function AppShell() {
  const { user, logout, isGuest } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const location = useLocation()
  const navigate = useNavigate()
  // 移动端「我的」抽屉是否展开
  const [meOpen, setMeOpen] = useState(false)
  // 桌面端游客面板（点「游客 ?」展开登录/注册入口）是否展开
  const [guestPanelOpen, setGuestPanelOpen] = useState(false)
  // 桌面端边栏是否折叠
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })

  const meActive = isMeActive(location.pathname)

  // 游客态下「不可用项」统一走这里：不跳转，改为展开登录入口（D43 不弹确认）
  const handleLockedNav = (e) => {
    e.preventDefault()
    setGuestPanelOpen(true)
    setMeOpen(true)
  }

  // 持久化折叠状态
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      // 忽略写入失败
    }
  }, [collapsed])

  const toggleCollapsed = () => setCollapsed((v) => !v)

  return (
    <div className={styles.shell}>
      {/* ===== 桌面:左侧边栏 ===== */}
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        {/* 品牌区 */}
        <div className={styles.brand}>
          <img
            src={theme === 'night' ? '/brand/logo-mark-on-dark.png' : '/brand/logo-mark-on-light.png'}
            alt=""
            className={styles.logo}
          />
          {!collapsed && <span className={styles.brandText}>EpochX</span>}
        </div>

        {/* 主导航 */}
        <nav className={styles.nav} aria-label="主导航">
          {PRIMARY_NAV.map((item) => {
            const locked = isGuest && item.guestBlocked
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={locked ? handleLockedNav : undefined}
                className={({ isActive }) =>
                  [
                    styles.navLink,
                    isActive && !locked ? styles.navLinkActive : '',
                    locked ? styles.navLinkLocked : '',
                  ]
                    .filter(Boolean)
                    .join(' ')
                }
                title={locked ? '游客试用不可用，登录后开启' : collapsed ? item.label : undefined}
                aria-disabled={locked || undefined}
              >
                <span className={styles.navIcon}>
                  <Icon name={item.icon} />
                </span>
                {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
                {!collapsed && locked && <span className={styles.navLock}>需登录</span>}
              </NavLink>
            )
          })}

          {/* 「我的」分组 */}
          <div className={styles.navDivider} />
          {ME_NAV.map((item) => {
            const locked = isGuest
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={locked ? handleLockedNav : undefined}
                className={({ isActive }) =>
                  [
                    styles.navLink,
                    isActive && !locked ? styles.navLinkActive : '',
                    locked ? styles.navLinkLocked : '',
                  ]
                    .filter(Boolean)
                    .join(' ')
                }
                title={locked ? '游客试用不可用，登录后开启' : collapsed ? item.label : undefined}
                aria-disabled={locked || undefined}
              >
                <span className={styles.navIcon}>
                  <Icon name={item.icon} />
                </span>
                {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
              </NavLink>
            )
          })}
        </nav>

        {/* 底部操作区 */}
        <div className={styles.sidebarFooter}>
          {/* 主题切换:SVG 太阳/月亮图标 */}
          <button
            type="button"
            className={styles.footerButton}
            onClick={toggleTheme}
            aria-label={theme === 'day' ? '切换到夜间模式' : '切换到日间模式'}
            title={collapsed ? (theme === 'day' ? '夜间模式' : '日间模式') : undefined}
          >
            <span className={styles.footerIcon}>
              {theme === 'day' ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="12" cy="12" r="4" fill="currentColor" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" />
                </svg>
              )}
            </span>
            {!collapsed && <span className={styles.footerLabel}>{theme === 'day' ? '日间' : '夜间'}</span>}
          </button>

          {/* 身份区：游客态显示「游客 ?」（点开即登录/注册入口，D43 常驻出口）；
              登录态显示邮箱。 */}
          {!collapsed && (isGuest ? (
            <button
              type="button"
              className={styles.guestBadge}
              onClick={() => setGuestPanelOpen((v) => !v)}
              aria-expanded={guestPanelOpen}
              title="当前为游客试用：不保存数据、不能使用 AI 功能"
            >
              游客 <span className={styles.guestQ}>?</span>
            </button>
          ) : user?.email ? (
            <div className={styles.userEmail} title={user.email}>
              {user.email}
            </div>
          ) : null)}

          {/* 游客面板：登录 / 注册入口（不弹确认，清爽切换，D43） */}
          {isGuest && guestPanelOpen && (
            <div className={styles.guestPanel} role="dialog" aria-label="转登录或注册">
              <p className={styles.guestPanelTitle}>当前为游客试用</p>
              <p className={styles.guestPanelHint}>
                不保存任何数据、不能使用 AI 功能。登录后试用数据会清空。
              </p>
              <div className={styles.guestPanelActions}>
                <button
                  type="button"
                  className={styles.guestActionPrimary}
                  onClick={() => { setGuestPanelOpen(false); navigate('/login') }}
                >
                  登录
                </button>
                <button
                  type="button"
                  className={styles.guestAction}
                  onClick={() => { setGuestPanelOpen(false); navigate('/register') }}
                >
                  注册
                </button>
              </div>
            </div>
          )}

          {/* 退出登录：仅登录态显示（游客用上面的「登录 / 注册」出口） */}
          {!isGuest && (
            <button
              type="button"
              className={styles.footerButton}
              onClick={logout}
              title={collapsed ? '退出登录' : undefined}
            >
              <span className={styles.footerIcon}>
                <Icon name="logout" />
              </span>
              {!collapsed && <span className={styles.footerLabel}>退出</span>}
            </button>
          )}

          {/* 折叠按钮 */}
          <button
            type="button"
            className={`${styles.footerButton} ${styles.collapseButton}`}
            onClick={toggleCollapsed}
            aria-label={collapsed ? '展开边栏' : '折叠边栏'}
            title={collapsed ? '展开边栏' : '折叠边栏'}
          >
            <span className={styles.footerIcon}>
              <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} />
            </span>
            {!collapsed && <span className={styles.footerLabel}>折叠</span>}
          </button>
        </div>
      </aside>

      {/* ===== 内容区 ===== */}
      <main className={`${styles.content} ${collapsed ? styles.contentCollapsed : ''}`}>
        <PageTransition />
      </main>

      {/* ===== 移动端:底部 Tab ===== */}
      <nav className={styles.tabbar} aria-label="底部导航">
        {PRIMARY_NAV.map((item) => {
          const locked = isGuest && item.guestBlocked
          return (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={locked ? handleLockedNav : undefined}
              className={({ isActive }) =>
                `${styles.tab} ${isActive && !locked ? styles.tabActive : ''} ${locked ? styles.tabLocked : ''}`
              }
              title={locked ? '游客试用不可用，登录后开启' : undefined}
              aria-disabled={locked || undefined}
            >
              <span className={styles.tabIcon}>
                <Icon name={item.icon} />
              </span>
              <span className={styles.tabLabel}>{item.label}</span>
            </NavLink>
          )
        })}
        <button
          type="button"
          className={`${styles.tab} ${meActive ? styles.tabActive : ''}`}
          onClick={() => setMeOpen((v) => !v)}
          aria-current={meActive ? 'page' : undefined}
        >
          <span className={styles.tabIcon}>
            <Icon name="profile" />
          </span>
          <span className={styles.tabLabel}>我的</span>
        </button>
      </nav>

      {/* 移动端「我的」抽屉 */}
      {meOpen && (
        <>
          <div className={styles.sheetMask} onClick={() => setMeOpen(false)} aria-hidden="true" />
          <div className={styles.sheet} role="menu">
            {isGuest && (
              <div className={styles.sheetGuest}>
                <p className={styles.sheetGuestTitle}>当前为游客试用</p>
                <p className={styles.sheetGuestHint}>不保存数据、不能使用 AI 功能。</p>
                <div className={styles.sheetGuestActions}>
                  <NavLink className={styles.sheetGuestPrimary} to="/login" onClick={() => setMeOpen(false)}>
                    登录
                  </NavLink>
                  <NavLink className={styles.sheetGuestSecondary} to="/register" onClick={() => setMeOpen(false)}>
                    注册
                  </NavLink>
                </div>
              </div>
            )}
            {ME_NAV.map((it) => {
              const locked = isGuest
              return (
                <NavLink
                  key={it.to}
                  to={it.to}
                  role="menuitem"
                  onClick={() => setMeOpen(false)}
                  className={({ isActive }) =>
                    `${styles.sheetItem} ${isActive ? styles.sheetItemActive : ''} ${locked ? styles.sheetItemLocked : ''}`
                  }
                  aria-disabled={locked || undefined}
                >
                  <span className={styles.sheetIcon}>
                    <Icon name={it.icon} />
                  </span>
                  {it.label}
                </NavLink>
              )
            })}
            <button type="button" className={styles.sheetItem} onClick={toggleTheme}>
              <span className={styles.sheetIcon}>
                {theme === 'day' ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="4" fill="currentColor" />
                    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" />
                  </svg>
                )}
              </span>
              {theme === 'day' ? '切换到夜间' : '切换到日间'}
            </button>
            {!isGuest && (
              <button type="button" className={styles.sheetItem} onClick={logout}>
                <span className={styles.sheetIcon}>
                  <Icon name="logout" />
                </span>
                退出登录
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

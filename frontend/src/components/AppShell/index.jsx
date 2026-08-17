/**
 * 四个业务页面共用的顶部导航条。只包裹 /personal-data /study-guide /study-plan
 * /study-timer 这四条路由（见 App.jsx），登录/注册/找回密码页保持原样不受影响。
 *
 * 刻意做得窄而透明（毛玻璃底），不覆盖各页面自己的视觉设计——这次整合的范围
 * 只到「能跳转 + 能看到登录态」，不统一队友页面内部的配色/字体/背景。
 */

import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import styles from './index.module.css'

const NAV_ITEMS = [
  { to: '/personal-data', label: '个人数据' },
  { to: '/study-guide', label: '导学计划' },
  { to: '/study-plan', label: '编辑计划' },
  { to: '/study-timer', label: '专注计时' },
  { to: '/settings', label: '设置' },
  { to: '/summary-review', label: '学习复盘' },
  { to: '/recommendations', label: '学习建议' },
  { to: '/profile-setup', label: '资料建档' },
  { to: '/guardian-auth', label: '监护人授权' },
]

export default function AppShell() {
  const { user, logout } = useAuth()

  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <div className={styles.brand}>
          <img src="/brand/logo-mark-on-light.png" alt="" className={styles.logo} />
          <span className={styles.brandText}>EpochX</span>
        </div>

        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={styles.account}>
          {user?.email ? <span className={styles.email}>{user.email}</span> : null}
          <button type="button" className={styles.logoutButton} onClick={logout}>
            退出登录
          </button>
        </div>
      </header>

      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  )
}

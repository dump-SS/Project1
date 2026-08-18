/**
 * 业务页共用外壳：顶部导航（桌面）+ 底部 Tab（移动端）。
 *
 * v0.2 信息架构：把原先 9 项平铺导航收敛为 4 个一级组（今日 / 我的数据 / 目标 / 我的），
 * 低频的设置/建档/授权收进「我的」。路由路径与页面本身不变，仅调整导航呈现结构。
 *
 * - 桌面：顶栏显示 4 个一级组；多页组 hover/focus 展开二级玻璃下拉。
 * - 移动：底部固定 4 Tab；多页组点开二级抽屉，单页组直接跳转。
 * 登录/注册/找回密码页不套此外壳，保持原样。
 */

import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import styles from './index.module.css'

// 一级组 → 二级项。single=true 表示该组只有一个页面，一级项本身即链接。
const NAV_GROUPS = [
  {
    key: 'today',
    label: '今日',
    to: '/study-guide',
    items: [
      { to: '/study-guide', label: '导学计划' },
      { to: '/study-timer', label: '专注计时' },
    ],
  },
  {
    key: 'data',
    label: '我的数据',
    to: '/personal-data',
    items: [
      { to: '/personal-data', label: '个人数据' },
      { to: '/summary-review', label: '学习复盘' },
      { to: '/recommendations', label: '学习建议' },
    ],
  },
  {
    key: 'goals',
    label: '目标',
    to: '/goals',
    single: true,
    items: [{ to: '/goals', label: '学习目标' }],
  },
  {
    key: 'me',
    label: '我的',
    to: '/settings',
    items: [
      { to: '/settings', label: '设置' },
      { to: '/profile-setup', label: '资料建档' },
      { to: '/guardian-auth', label: '监护人授权' },
    ],
  },
]

function isGroupActive(group, pathname) {
  return group.items.some((it) => pathname.startsWith(it.to))
}

export default function AppShell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  // 移动端展开的组 key（null 表示抽屉关闭）
  const [openGroup, setOpenGroup] = useState(null)

  const handleTabClick = (group) => {
    if (group.single) {
      setOpenGroup(null)
      navigate(group.to)
    } else {
      setOpenGroup((prev) => (prev === group.key ? null : group.key))
    }
  }

  const activeGroup = NAV_GROUPS.find((g) => isGroupActive(g, location.pathname))

  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <div className={styles.brand}>
          <img src="/brand/logo-mark-on-light.png" alt="" className={styles.logo} />
          <span className={styles.brandText}>EpochX</span>
        </div>

        {/* 桌面顶栏：一级组 + 二级下拉（纯 CSS hover/focus 展开）*/}
        <nav className={styles.nav} aria-label="主导航">
          {NAV_GROUPS.map((group) =>
            group.single ? (
              <NavLink
                key={group.key}
                to={group.to}
                className={({ isActive }) =>
                  isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink
                }
              >
                {group.label}
              </NavLink>
            ) : (
              <div key={group.key} className={styles.navGroup}>
                <button
                  type="button"
                  className={`${styles.navLink} ${styles.navGroupTrigger} ${
                    activeGroup?.key === group.key ? styles.navLinkActive : ''
                  }`}
                  aria-haspopup="true"
                >
                  {group.label}
                </button>
                <div className={styles.dropdown} role="menu">
                  {group.items.map((it) => (
                    <NavLink
                      key={it.to}
                      to={it.to}
                      role="menuitem"
                      className={({ isActive }) =>
                        isActive
                          ? `${styles.dropdownItem} ${styles.dropdownItemActive}`
                          : styles.dropdownItem
                      }
                    >
                      {it.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            ),
          )}
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

      {/* 移动端底部 Tab */}
      <nav className={styles.tabbar} aria-label="底部导航">
        {NAV_GROUPS.map((group) => (
          <button
            key={group.key}
            type="button"
            className={`${styles.tab} ${activeGroup?.key === group.key ? styles.tabActive : ''}`}
            onClick={() => handleTabClick(group)}
            aria-current={activeGroup?.key === group.key ? 'page' : undefined}
          >
            {group.label}
          </button>
        ))}
      </nav>

      {/* 移动端二级抽屉 */}
      {openGroup && (
        <>
          <div className={styles.sheetMask} onClick={() => setOpenGroup(null)} aria-hidden="true" />
          <div className={styles.sheet} role="menu">
            {NAV_GROUPS.find((g) => g.key === openGroup)?.items.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                role="menuitem"
                className={({ isActive }) =>
                  isActive ? `${styles.sheetItem} ${styles.sheetItemActive}` : styles.sheetItem
                }
                onClick={() => setOpenGroup(null)}
              >
                {it.label}
              </NavLink>
            ))}
            <button type="button" className={styles.sheetItem} onClick={logout}>
              退出登录
            </button>
          </div>
        </>
      )}
    </div>
  )
}

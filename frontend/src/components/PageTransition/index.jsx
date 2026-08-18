/**
 * 同级页面过渡容器
 *
 * 监听 useLocation().pathname 变化,给内容容器加 key,
 * 触发 CSS 动画:旧内容淡出(0.2s)→ 新内容从右侧滑入(0.3s)。
 *
 * 使用方式:包在 AppShell 的 <main> 里,替换直接的 <Outlet />。
 */

import { useEffect, useRef, useState } from 'react'
import { useLocation, Outlet } from 'react-router-dom'
import styles from './index.module.css'

export default function PageTransition() {
  const location = useLocation()
  const [displayLocation, setDisplayLocation] = useState(location)
  const [transitionStage, setTransitionStage] = useState('enter') // 'enter' | 'exit'
  const prevPathRef = useRef(location.pathname)

  useEffect(() => {
    if (location.pathname === prevPathRef.current) return

    // 旧内容淡出
    setTransitionStage('exit')
    const exitTimer = setTimeout(() => {
      setDisplayLocation(location)
      prevPathRef.current = location.pathname
      setTransitionStage('enter')
    }, 200) // 与 CSS 中 exit 动画时长一致

    return () => clearTimeout(exitTimer)
  }, [location])

  return (
    <div
      key={displayLocation.pathname}
      className={`${styles.transition} ${
        transitionStage === 'exit' ? styles.transitionExit : styles.transitionEnter
      }`}
    >
      <Outlet />
    </div>
  )
}

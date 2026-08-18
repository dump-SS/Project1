/**
 * 主题切换云层过渡
 *
 * 监听 theme 变化,切换时全屏写实云层从左向右飘过,云层下方是新主题。
 * 时长 600ms,与 tokens.css --t-theme 一致。
 *
 * 实现:监听 useTheme().theme,变化时设置 isActive=true,
 * 600ms 后关闭。多层云以不同速度移动,产生纵深感。
 */

import { useEffect, useRef, useState } from 'react'
import { useTheme } from '../../context/ThemeContext.jsx'
import styles from './index.module.css'

const TRANSITION_DURATION = 600 // 与 tokens.css --t-theme 一致

export default function CloudTransition() {
  const { theme } = useTheme()
  const [isActive, setIsActive] = useState(false)
  const prevThemeRef = useRef(theme)

  useEffect(() => {
    if (theme === prevThemeRef.current) return
    prevThemeRef.current = theme

    setIsActive(true)
    const timer = setTimeout(() => {
      setIsActive(false)
    }, TRANSITION_DURATION)

    return () => clearTimeout(timer)
  }, [theme])

  if (!isActive) return null

  return (
    <div className={styles.cloudTransition} aria-hidden="true">
      <div className={`${styles.cloud} ${styles.cloudBack}`} />
      <div className={`${styles.cloud} ${styles.cloudMid}`} />
      <div className={`${styles.cloud} ${styles.cloudFront}`} />
    </div>
  )
}

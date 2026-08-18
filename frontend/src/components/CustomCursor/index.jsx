/**
 * 自定义光标 · 桌面端生效
 *
 * - 8px 圆点,半透明主题色边框 + 白色填充
 * - hover 可点击元素时放大到 20px 并变为实心
 * - 触屏设备(hover: none)不渲染
 *
 * 实现:
 * - 监听全局 mousemove,用 requestAnimationFrame 平滑跟随
 * - 监听 mouseover/mouseout,判断 target 是否匹配可点击选择器
 * - 桌面端通过 CSS 隐藏原生光标(body.cursor-hidden *)
 */

import { useEffect, useRef, useState } from 'react'
import styles from './index.module.css'

const CLICKABLE_SELECTOR =
  'a, button, [role="button"], input, textarea, select, label, [data-clickable], [class*="navLink"], [class*="tab"], [class*="dropdownItem"], [class*="sheetItem"]'

export default function CustomCursor() {
  const cursorRef = useRef(null)
  const [isVisible, setIsVisible] = useState(false)
  const [isHovering, setIsHovering] = useState(false)
  const positionRef = useRef({ x: 0, y: 0 })
  const rafRef = useRef(null)

  useEffect(() => {
    // 触屏设备不启用
    if (typeof window === 'undefined') return
    if (window.matchMedia('(hover: none)').matches) return

    const cursor = cursorRef.current
    if (!cursor) return

    // 显示自定义光标,隐藏原生光标
    document.body.classList.add('cursor-hidden')
    setIsVisible(true)

    const handleMouseMove = (e) => {
      positionRef.current = { x: e.clientX, y: e.clientY }
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(() => {
          if (cursorRef.current) {
            cursorRef.current.style.transform = `translate(${positionRef.current.x}px, ${positionRef.current.y}px)`
          }
          rafRef.current = null
        })
      }
    }

    const handleMouseOver = (e) => {
      if (e.target.closest(CLICKABLE_SELECTOR)) {
        setIsHovering(true)
      }
    }

    const handleMouseOut = (e) => {
      if (e.target.closest(CLICKABLE_SELECTOR)) {
        setIsHovering(false)
      }
    }

    const handleMouseLeave = () => {
      setIsVisible(false)
    }

    const handleMouseEnter = () => {
      setIsVisible(true)
    }

    window.addEventListener('mousemove', handleMouseMove, { passive: true })
    document.addEventListener('mouseover', handleMouseOver, { passive: true })
    document.addEventListener('mouseout', handleMouseOut, { passive: true })
    document.documentElement.addEventListener('mouseleave', handleMouseLeave)
    document.documentElement.addEventListener('mouseenter', handleMouseEnter)

    return () => {
      document.body.classList.remove('cursor-hidden')
      window.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseover', handleMouseOver)
      document.removeEventListener('mouseout', handleMouseOut)
      document.documentElement.removeEventListener('mouseleave', handleMouseLeave)
      document.documentElement.removeEventListener('mouseenter', handleMouseEnter)
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [])

  // 触屏设备直接不渲染
  if (typeof window !== 'undefined' && window.matchMedia('(hover: none)').matches) {
    return null
  }

  return (
    <div
      ref={cursorRef}
      className={`${styles.cursor} ${isVisible ? styles.cursorVisible : ''} ${
        isHovering ? styles.cursorHover : ''
      }`}
      aria-hidden="true"
    />
  )
}

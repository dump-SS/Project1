// 全局主题(日/夜)状态。
// 默认遵循系统偏好,用户手动切换后持久化到 localStorage。
// 切换时给 <html> 加 .theme-transition 类,触发 tokens.css 里定义的 0.6s 全站过渡。
//
// 使用方式:
//   const { theme, toggleTheme } = useTheme()
//   theme === 'day' | 'night'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const ThemeContext = createContext(null)

const STORAGE_KEY = 'epochx-theme'
const TRANSITION_MS = 600 // 与 tokens.css --t-theme 保持一致

function getInitialTheme() {
  if (typeof window === 'undefined') return 'day'
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved === 'day' || saved === 'night') return saved
  } catch {
    // localStorage 可能被禁用,静默降级
  }
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'night' : 'day'
  }
  return 'day'
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme)

  // 同步 [data-theme] 到 <html>,并触发一次性过渡动画
  useEffect(() => {
    const root = document.documentElement
    root.classList.add('theme-transition')
    root.setAttribute('data-theme', theme)
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // 忽略写入失败
    }
    const timer = setTimeout(() => {
      root.classList.remove('theme-transition')
    }, TRANSITION_MS)
    return () => clearTimeout(timer)
  }, [theme])

  // 监听系统偏好变化(仅当用户未手动指定过时跟随)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY)
        // 用户已经手动选过就不再跟随系统
        if (saved === 'day' || saved === 'night') return
      } catch {
        // 继续跟随系统
      }
      setTheme(e.matches ? 'night' : 'day')
    }
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', handler)
      return () => media.removeEventListener('change', handler)
    }
    return undefined
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'day' ? 'night' : 'day'))
  }, [])

  const value = useMemo(() => ({ theme, toggleTheme }), [theme, toggleTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme 必须在 <ThemeProvider> 内部使用')
  }
  return ctx
}

import { useEffect, useRef, useState } from 'react'

/**
 * sticky 容器内的滚动进度（0 → 1），用于第二屏视窗、功能屏切换等滚动驱动动效。
 * 容器高度 = 视口高 + pinRange（外层撑出的滚动跑道）。
 */
export function useScrollProgress<T extends HTMLElement>(): [
  React.RefObject<T | null>,
  number,
] {
  const ref = useRef<T | null>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    let raf = 0

    const update = () => {
      raf = 0
      const rect = el.getBoundingClientRect()
      const total = rect.height - window.innerHeight
      if (total <= 0) {
        setProgress(rect.top <= 0 ? 1 : 0)
        return
      }
      // top 从 innerHeight（刚进入）走到 -total（滚完），映射到 0→1
      const p = (window.innerHeight - rect.top) / (window.innerHeight + total)
      setProgress(Math.min(1, Math.max(0, p)))
    }

    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }

    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])

  return [ref, progress]
}

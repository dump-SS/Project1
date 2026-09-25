import { useEffect, useRef, useState } from 'react'

/**
 * 元素进入视口检测（重动效按屏懒加载用，dev-spec §2.3）。
 * @param rootMargin 提前量，默认进入前 20% 视口高度就开始加载
 */
export function useInView<T extends HTMLElement>(
  rootMargin = '20% 0px',
  once = true,
): [React.RefObject<T>, boolean] {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      // 无 IO 环境直接视为可见（静态兜底在上层处理）
      setInView(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          if (once) io.disconnect()
        } else if (!once) {
          setInView(false)
        }
      },
      { rootMargin },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [rootMargin, once])

  return [ref, inView]
}

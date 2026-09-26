import { useEffect, useRef, useState } from 'react'

/**
 * 元素进入视口检测（重动效按屏懒加载用，dev-spec §2.3）。
 * @param rootMargin 提前量，默认进入前 20% 视口高度就开始加载
 *
 * ⚠️ **兜底（2026-09-25，必须有，别删）**：本仓实测 IntersectionObserver 会漏回调；
 * 更狠的是预览/低活跃环境里 `requestAnimationFrame` 可能整段不派发（合成器冻结），
 * 而叙事屏 `.section` 的未入场态是 `opacity: 0`——任何一环失效就是整屏空白。
 * 所以这里三重保险，且**最后一道不依赖任何异步回调**：
 *   ① IntersectionObserver（正常浏览器就是它生效，时序最准）；
 *   ② scroll / resize 上的 rAF 节流复查（IO 漏回调时补）；
 *   ③ **1s `setInterval` 里同步 `getBoundingClientRect` 复查**——rAF 被冻结也能工作。
 * 命中后 `stop()` 摘掉全部监听与定时器，稳态零开销。
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

    let done = false
    let raf = 0
    let timer = 0

    const stop = () => {
      io.disconnect()
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      window.clearInterval(timer)
      if (raf) cancelAnimationFrame(raf)
    }
    const hit = () => {
      if (done) return
      done = true
      setInView(true)
      if (once) stop()
    }
    /** 同步判否在视口内（不依赖 rAF/事件） */
    const checkNow = () => {
      if (done) return
      const rect = el.getBoundingClientRect()
      const vh = window.innerHeight || 0
      if (rect.top < vh && rect.bottom > 0) hit()
      else if (!once) setInView(false)
    }
    /** 滚动/改窗用的 rAF 节流版（避免高频 rect 读） */
    const onScroll = () => {
      if (raf || done) return
      raf = requestAnimationFrame(() => {
        raf = 0
        checkNow()
      })
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) hit()
        else if (!once) setInView(false)
      },
      { rootMargin },
    )
    io.observe(el)
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    // 最后一道：同步复查，连 rAF 都不依赖
    timer = window.setInterval(checkNow, 1000)
    checkNow()

    return () => {
      done = true
      stop()
    }
  }, [rootMargin, once])

  return [ref, inView]
}

import { useEffect, useRef } from 'react'

/**
 * Hero 暗纹层「手电」（2026-09-25 Skyer 调整：监听提到 window 级）。
 * 机制：跟随指针位置写 CSS 变量 --lp-torch-x/y，暗纹层的亮度洞
 * （backdrop-filter，见 Hero.module.css .torchHole）随之提亮指针附近的图标。
 *
 * ⚠️ 监听必须在 window 上：原来挂在 Hero section 上时，光标移到顶栏
 * （fixed，不是 section 后代）后事件不再到达 section，手电即失效。
 * 坐标仍按 section 几何换算，指针在页面任意位置（含顶栏）都有效。
 *
 * 降级（dev-spec §6）：
 * - 触屏 / 无 hover：由调用方判断（matchMedia '(hover: none)'），暗纹低辨识度常亮；
 * - 指针离开文档（documentElement mouseleave）→ 变量归 -9999（光熄灭）。
 */
export function useFlashlight<T extends HTMLElement>(enabled: boolean): React.RefObject<T> {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    if (!enabled) return
    const el = ref.current
    if (!el) return
    if (window.matchMedia('(hover: none)').matches) return

    const onMove = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect()
      el.style.setProperty('--lp-torch-x', `${e.clientX - rect.left}px`)
      el.style.setProperty('--lp-torch-y', `${e.clientY - rect.top}px`)
    }
    const onLeave = () => {
      el.style.setProperty('--lp-torch-x', '-9999px')
      el.style.setProperty('--lp-torch-y', '-9999px')
    }

    window.addEventListener('pointermove', onMove, { passive: true })
    document.documentElement.addEventListener('mouseleave', onLeave)
    return () => {
      window.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('mouseleave', onLeave)
    }
  }, [enabled])

  return ref
}

/** 是否具备精确指针（触屏则暗纹低辨识度常亮，不开手电） */
export function hasHoverPointer(): boolean {
  if (typeof window === 'undefined') return false
  return !window.matchMedia('(hover: none)').matches
}

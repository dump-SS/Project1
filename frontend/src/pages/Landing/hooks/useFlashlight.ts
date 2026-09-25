import { useEffect, useRef } from 'react'

/**
 * Hero 暗纹层「手电」（visual-language §7.1，仅 Hero 使用，不推广到卡片/截图）。
 * 机制：监听容器 pointer 位置 → 写 CSS 变量 --lp-torch-x/y → 暗纹层用
 * radial-gradient mask 让鼠标附近 1.5px 线稿显形（静止时近不可见）。
 *
 * 降级（dev-spec §6）：
 * - 触屏 / 无 hover：由调用方判断（matchMedia '(hover: none)'），常亮低辨识度暗纹；
 * - prefers-reduced-motion：本 hook 无动画帧，仅跟随指针，无需额外处理；
 *   但视觉上暗纹显形属交互反馈而非运动，保留。
 */
export function useFlashlight<T extends HTMLElement>(enabled: boolean) {
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
      // 离开容器 → 光熄灭（半径归零，暗纹回到近不可见）
      el.style.setProperty('--lp-torch-x', '-9999px')
      el.style.setProperty('--lp-torch-y', '-9999px')
    }

    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    return () => {
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
    }
  }, [enabled])

  return ref
}

/** 是否具备精确指针（触屏则暗纹低辨识度常亮，不开手电） */
export function hasHoverPointer(): boolean {
  if (typeof window === 'undefined') return false
  return !window.matchMedia('(hover: none)').matches
}

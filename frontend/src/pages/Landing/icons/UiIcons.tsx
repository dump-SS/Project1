/**
 * UI 小图标（返回顶部 / 展开箭头 / 外部链接）。
 * 统一规格同 DarkMotifs。
 */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function base({ size = 24, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...rest,
  }
}

/** 返回顶部箭头 */
export function IconArrowUp(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 20V5M6 11l6-6 6 6" />
    </svg>
  )
}

/** 展开箭头（下指，展开后由 CSS 翻转） */
export function IconChevronDown(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="m6 9.5 6 6 6-6" />
    </svg>
  )
}

/** 外部链接 */
export function IconExternal(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14 5h5v5M19 5l-8 8" />
      <path d="M19 14v5a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h5" />
    </svg>
  )
}

/** 发送（小纸飞机，CTA 胶囊输入框右侧发送键） */
export function IconSend(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M21.5 2.5 2.6 10.4l7.6 3.2 3.2 7.6z" />
      <path d="M21.5 2.5 10.2 13.6" />
    </svg>
  )
}

/**
 * 信任屏卡片图标（2026-09-25 Skyer 指定）：锁头 / 柱状图 / 回箭头 / 带感叹号盾牌。
 * monoline 风格与 DarkMotifs 一致（24×24 / stroke 1.5 / 圆角端点），
 * 但描边走**品牌色渐变**（#8FD3E8 → #4AD1FF → #1B5DBF）。
 * 渐变 id 由 useId 生成，避免多实例冲突。
 */
import { useId } from 'react'

type IconProps = { size?: number; className?: string }

function useGradientId(tag: string) {
  return `trust-${tag}-${useId().replace(/:/g, '')}`
}

function Svg({
  size = 28,
  className,
  gradientId,
  children,
}: IconProps & { gradientId: string; children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <defs>
        {/* userSpaceOnUse：零宽/零高的直线路径（如柱状图的竖线）在
            objectBoundingBox 下包围盒退化、渐变失效导致整组线不渲染 */}
        <linearGradient
          id={gradientId}
          gradientUnits="userSpaceOnUse"
          x1="2"
          y1="2"
          x2="22"
          y2="22"
        >
          <stop offset="0%" stopColor="#8FD3E8" />
          <stop offset="50%" stopColor="#4AD1FF" />
          <stop offset="100%" stopColor="#1B5DBF" />
        </linearGradient>
      </defs>
      <g stroke={`url(#${gradientId})`} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
        {children}
      </g>
    </svg>
  )
}

/** 数据不出境：锁头 */
export function IconLock({ size, className }: IconProps) {
  const id = useGradientId('lock')
  return (
    <Svg size={size} className={className} gradientId={id}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
      <path d="M12 14.5v2.5" />
    </Svg>
  )
}

/** 不评判·不排名：柱状图 */
export function IconBars({ size, className }: IconProps) {
  const id = useGradientId('bars')
  return (
    <Svg size={size} className={className} gradientId={id}>
      <path d="M4 20h16" />
      <path d="M6.5 20v-5.5" />
      <path d="M11 20v-9" />
      <path d="M15.5 20v-13" />
      <path d="M20 20V9.5" />
    </Svg>
  )
}

/** 监护人可撤回：回箭头 */
export function IconReturn({ size, className }: IconProps) {
  const id = useGradientId('return')
  return (
    <Svg size={size} className={className} gradientId={id}>
      <path d="M9 14 4 9l5-5" />
      <path d="M4 9h9a7 7 0 0 1 7 7v4" />
    </Svg>
  )
}

/** 不替你做决定：带感叹号的盾牌 */
export function IconShieldAlert({ size, className }: IconProps) {
  const id = useGradientId('shield')
  return (
    <Svg size={size} className={className} gradientId={id}>
      <path d="M12 3.5 19 6v5.5c0 4.2-2.9 7.4-7 9-4.1-1.6-7-4.8-7-9V6l7-2.5Z" />
      <path d="M12 9v4.2" />
      <path d="M12 16.2h.01" />
    </Svg>
  )
}

/**
 * 功能图标（图标海屏 · 顺序 = 学生的一天）。
 * 统一规格同 DarkMotifs：monoline · 24×24 · stroke 1.5 · currentColor · 无填充 · 圆角端点。
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

/** 计划：清单 + 勾选 */
export function IconPlan(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="m8 9 1.5 1.5L12 8M8 15h8M14.5 9H16" />
    </svg>
  )
}

/** 计时：时钟 + 砂点 */
export function IconTimer(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="13" r="7.5" />
      <path d="M12 9.5V13l2.5 2M9.5 3h5" />
    </svg>
  )
}

/** 记录：笔记 + 笔 */
export function IconRecord(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H16l3 3v13.5A1.5 1.5 0 0 1 17.5 21h-11A1.5 1.5 0 0 1 5 19.5v-15Z" />
      <path d="M15 3v3.5h3.5M8.5 12h7M8.5 16h4" />
    </svg>
  )
}

/** 错题：错号 + 索引标签 */
export function IconErrorMark(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </svg>
  )
}

/** 知识点：节点 + 连线（图谱意象，非宇宙） */
export function IconKnowledge(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="18" cy="8" r="2.2" />
      <circle cx="10" cy="18" r="2.2" />
      <path d="M8.1 6.8 15.9 7.9M16.8 10 11.6 16.2M8.1 7.8 9 16" />
    </svg>
  )
}

/** 复盘：回望箭头（逆时针） */
export function IconReview(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 5v5h5" />
      <path d="M4.5 10a8 8 0 1 1-1 4.5" />
    </svg>
  )
}

/** Chat：对话气泡 */
export function IconChat(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 4v-4H7a3 3 0 0 1-3-3V6Z" />
      <path d="M8.5 8.5h7M8.5 11.5h4" />
    </svg>
  )
}

/** 收藏：书签 */
export function IconBookmark(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M7 3.5h10a1 1 0 0 1 1 1V21l-6-3.5L6 21V4.5a1 1 0 0 1 1-1Z" />
    </svg>
  )
}

/** 学生的一天 · 图标海顺序映射 */
export const SEA_ICONS = [
  IconPlan,
  IconTimer,
  IconRecord,
  IconErrorMark,
  IconKnowledge,
  IconReview,
  IconChat,
  IconBookmark,
] as const

/**
 * 暗纹物件图标（Hero 背景 + 功能屏主题物件）。
 * 统一规格（dev-spec §5.1）：monoline 线稿 · viewBox 0 0 24 24 · stroke 1.5 ·
 * currentColor · 无填充 · 圆角端点。
 * 题材红线（visual-language §2）：全是学科物件，非宇宙。
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

/** 成绩单：纸张 + 三行分数条 */
export function IconReportCard(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 8h8M8 12h5M8 16h6" />
      <circle cx="16.5" cy="12" r="1" />
      <circle cx="15.5" cy="16" r="1" />
    </svg>
  )
}

/** 书：摊开的书本 */
export function IconBook(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 6c-1.8-1.6-4.2-2-7-2v14c2.8 0 5.2.4 7 2 1.8-1.6 4.2-2 7-2V4c-2.8 0-5.2.4-7 2Z" />
      <path d="M12 6v14" />
    </svg>
  )
}

/** 笔记本：封面 + 螺旋线圈 */
export function IconNotebook(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M8 3v3M12 3v3M16 3v3M8 18h6" />
    </svg>
  )
}

/** 铅笔 */
export function IconPencil(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="m4 20 1.2-4.2L15.8 5.2a2 2 0 0 1 2.8 0l.2.2a2 2 0 0 1 0 2.8L8.2 18.8 4 20Z" />
      <path d="m14 7 3 3" />
    </svg>
  )
}

/** 直尺：斜放刻度尺 */
export function IconRuler(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="1.8" y="8.6" width="20.4" height="6.8" rx="1.2" transform="rotate(-30 12 12)" />
      <path d="m7.2 12.2 1.3 2.2M10.4 10.4l.9 1.5M13.3 8.7l1.3 2.2M16.5 6.9l.9 1.5" />
    </svg>
  )
}

/** 圆规 */
export function IconCompass(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="4.5" r="1.5" />
      <path d="M12 6 6.5 20M12 6l5.5 14" />
      <path d="M8.6 14.5a6.5 6.5 0 0 0 6.8 0" />
    </svg>
  )
}

/** 三角板 */
export function IconTriangle(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19 12 4l8 15H4Z" />
      <path d="M9 15h6" />
    </svg>
  )
}

/** 锥形瓶 */
export function IconFlask(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9.5 3h5M10 3v5.5L4.8 18a2 2 0 0 0 1.8 3h10.8a2 2 0 0 0 1.8-3L14 8.5V3" />
      <path d="M7.5 15h9" />
    </svg>
  )
}

/** 烧杯 */
export function IconBeaker(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M7 3h10M8 3v14a4 4 0 0 0 4 4 4 4 0 0 0 4-4V3" />
      <path d="M8.5 11c2 1 4.5-1 7 0" />
    </svg>
  )
}

/** 试管 */
export function IconTestTube(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9 3h6M9.5 3v14a2.5 2.5 0 0 0 5 0V3" />
      <path d="M9.5 12.5a2.5 2.5 0 0 0 5 .5" />
    </svg>
  )
}

/** 地球仪：支架 + 经纬线 */
export function IconGlobe(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="10" r="6.5" />
      <path d="M5.5 10h13M12 3.5c-2.5 2-2.5 11 0 13 2.5-2 2.5-11 0-13Z" />
      <path d="M9 20.5h6M12 16.5v4" />
    </svg>
  )
}

/** 显微镜 */
export function IconMicroscope(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M10 4.5 13.5 3l2 4.5-3.5 1.5L10 4.5Z" />
      <path d="M12.2 9 10 14a4 4 0 1 0 7 3" />
      <path d="M8 21h10M6.5 17.5h4" />
    </svg>
  )
}

/** 秒表 */
export function IconStopwatch(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="13.5" r="7" />
      <path d="M12 10v3.5l2.5 1.5M10 3h4M12 3v3.5M18.5 8 20 6.5" />
    </svg>
  )
}

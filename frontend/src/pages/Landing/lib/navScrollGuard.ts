/**
 * 顶栏与各屏的滚动协调（模块级单例，落地页内部使用）。
 *
 * 1. hijackRange：信任屏横向劫持的纵向滚动区间。区间内顶栏滚动收起/弹出行为
 *    禁用（滚轮被劫持逻辑吃掉会导致判断抖动，visual-language §7.0）；
 * 2. footerInView：页尾进入视口 → 顶栏加深遮罩（不切文字颜色）。
 */
export interface HijackRange {
  top: number
  bottom: number
}

let hijackRange: HijackRange | null = null
const hijackListeners = new Set<() => void>()

export function setHijackRange(range: HijackRange | null) {
  hijackRange = range
  hijackListeners.forEach((fn) => fn())
}

export function getHijackRange() {
  return hijackRange
}

export function subscribeHijack(fn: () => void) {
  hijackListeners.add(fn)
  return () => hijackListeners.delete(fn)
}

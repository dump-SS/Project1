/**
 * 顶栏与各屏的滚动协调（模块级单例，落地页内部使用）。
 *
 * 1. lockRange：多个「顶栏锁定区间」——区间内顶栏强制常显，滚动收起/弹出行为
 *    禁用（sticky 冻结纵向滚动期间滚动事件停发，判断会抖动，visual-language §7.0）。
 *    2026-09-25 Skyer 扩展：改为按 owner 注册的区间表（原只支持单一区间），
 *    任一区间覆盖当前滚动位置即视为锁定中：
 *      · `epochs-lock`（第二屏）：跑道起点 → 梯形卡片收起点——锁定延后到与
 *        梯形卡片同步收起，卡片左滑出屏幕的同一刻解除锁定；
 *      · `trustwall`（信任屏）：横滚劫持全程。
 * 2. footerInView：页尾进入视口 → 顶栏加深遮罩（不切文字颜色）。
 */
export interface HijackRange {
  top: number
  bottom: number
}

const ranges = new Map<string, HijackRange>()
const hijackListeners = new Set<() => void>()

/** 按 owner 注册 / 解除锁定区间（range 传 null 表示解除该 owner） */
export function setHijackRange(owner: string, range: HijackRange | null) {
  if (range === null) {
    if (!ranges.has(owner)) return
    ranges.delete(owner)
  } else {
    ranges.set(owner, range)
  }
  hijackListeners.forEach((fn) => fn())
}

/** 是否存在已注册的锁定区间（useSyncExternalStore 取值必须是稳定快照） */
export function getHijackActive() {
  return ranges.size > 0
}

/** 当前滚动位置是否落在任一锁定区间内 */
export function isInHijack(y: number) {
  for (const r of ranges.values()) {
    if (y >= r.top && y <= r.bottom) return true
  }
  return false
}

export function subscribeHijack(fn: () => void) {
  hijackListeners.add(fn)
  return () => hijackListeners.delete(fn)
}

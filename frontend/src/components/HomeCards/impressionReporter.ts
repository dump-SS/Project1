/**
 * IntersectionObserver 回调的判定逻辑抽成纯函数，便于在 node 环境单测
 * 「真正进视口才报 shown」与「同卡反复进视口不重复报」两条硬要求（charter §四）。
 *
 * 组件侧只负责把真实 IntersectionObserverEntry 喂进来；判定不依赖 DOM。
 */

export interface ShownEntryLike {
  isIntersecting: boolean
  intersectionRatio: number
  target: { dataset?: { impressionKey?: string } } | null
}

export interface ShownReporter {
  (entries: ShownEntryLike[]): void
}

/**
 * @param isSeen  该指纹本轮是否已报过 shown
 * @param markSeen 记为已报
 * @param report  真正上报（组件侧接 service）
 */
export function createShownReporter(
  isSeen: (key: string) => boolean,
  markSeen: (key: string) => void,
  report: (key: string) => void,
): ShownReporter {
  return (entries) => {
    for (const entry of entries) {
      // 「真正进入视口」：isIntersecting 且比例 > 0（擦边 0 比例不算展示）
      if (!entry.isIntersecting || entry.intersectionRatio <= 0) continue
      const key = entry.target?.dataset?.impressionKey
      if (!key || isSeen(key)) continue
      markSeen(key)
      report(key)
    }
  }
}

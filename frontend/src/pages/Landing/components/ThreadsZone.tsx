import { lazy, Suspense, type ReactNode } from 'react'
import { useReducedMotion } from '../hooks/useReducedMotion'
import styles from './ThreadsZone.module.css'

// Threads（React Bits，ogl）：功能屏 ×3（叙事部分）的常驻背景光带
// （2026-09-25 Skyer 指定：amplitude 0.4 / distance 1，品牌蓝线条）。
// sticky 钉满视口、后续内容从其上滚过（.content z 抬升）；
// ogl 画布铺满 sticky 层，随三块内容滚动全程常驻、零 resize。
// reduced-motion 不挂载（透出页面深底）；组件内置 IO/可见性暂停。
const Threads = lazy(() => import('./bits/Threads'))

/** 品牌蓝 #4AD1FF → ogl 归一化 RGB */
const BRAND_BLUE: [number, number, number] = [0.29, 0.82, 1]

export default function ThreadsZone({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion()

  return (
    <div className={styles.zone}>
      {/* 常驻背景层：sticky 钉满视口；负 margin 使后续内容叠于其上 */}
      <div className={styles.sticky} aria-hidden>
        {!reduced && (
          <Suspense fallback={null}>
            <Threads color={BRAND_BLUE} amplitude={0.4} distance={1} />
          </Suspense>
        )}
        <div className={styles.fadeTop} aria-hidden />
        <div className={styles.fadeBottom} aria-hidden />
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  )
}

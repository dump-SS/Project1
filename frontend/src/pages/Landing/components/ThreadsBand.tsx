import { lazy, Suspense } from 'react'
import { useReducedMotion } from '../hooks/useReducedMotion'
import styles from './ThreadsBand.module.css'

// Threads（React Bits，ogl）：三时代 → 隐私安全之间的过渡带背景
// （2026-09-25 Skyer 指定：amplitude 1 / distance 0，品牌蓝线条）。
// reduced-motion 不挂载（纯深底带）；组件内置 IO/可见性暂停，滚出视口即停渲染。
const Threads = lazy(() => import('./bits/Threads'))

/** Threads 过渡带（2026-09-25 Skyer 指定）：amplitude 0.4 / distance 1，品牌蓝线条 */
const BRAND_BLUE: [number, number, number] = [0.29, 0.82, 1]

export default function ThreadsBand() {
  const reduced = useReducedMotion()

  return (
    <section className={styles.band} aria-hidden>
      {!reduced && (
        <Suspense fallback={null}>
          <Threads color={BRAND_BLUE} amplitude={0.4} distance={1} />
        </Suspense>
      )}
      <div className={styles.fadeTop} aria-hidden />
      <div className={styles.fadeBottom} aria-hidden />
    </section>
  )
}

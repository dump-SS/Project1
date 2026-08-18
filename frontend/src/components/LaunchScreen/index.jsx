/**
 * 开屏动画 · X(Twitter) 风格
 *
 * - Logo 从中心由小放大(scale 0.3 → 18),透过镂空能看到下方页面
 * - 放大到顶点后溶解消散(filter: blur + opacity 0),像云层散开
 * - 时长 1.5s,缓动 cubic-bezier(0.22, 1, 0.36, 1)(X 的弹簧感)
 * - localStorage 记录已播放,刷新页面后不再显示
 *
 * 触发方式:挂在 App 根部,首次挂载时渲染,动画结束后自动卸载。
 */

import { useEffect, useState } from 'react'
import styles from './index.module.css'

const STORAGE_KEY = 'epochx-launch-played'
const ANIMATION_DURATION = 1500 // 与 CSS 动画时长一致

export default function LaunchScreen() {
  const [shouldShow, setShouldShow] = useState(false)
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    // 已播放过则直接不渲染
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === '1') {
        return
      }
    } catch {
      // localStorage 不可用时仍然播放一次
    }
    setShouldShow(true)

    // 主动画结束后进入消散阶段
    const dissolveTimer = setTimeout(() => {
      setIsExiting(true)
    }, ANIMATION_DURATION - 300)

    // 完全结束后卸载 + 记录已播放
    const doneTimer = setTimeout(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, '1')
      } catch {
        // 忽略写入失败
      }
      setShouldShow(false)
    }, ANIMATION_DURATION + 400)

    return () => {
      clearTimeout(dissolveTimer)
      clearTimeout(doneTimer)
    }
  }, [])

  if (!shouldShow) return null

  return (
    <div
      className={`${styles.launchScreen} ${isExiting ? styles.launchScreenExiting : ''}`}
      aria-hidden="true"
    >
      {/* 镂空圆形视窗:透过它能看到下方页面逐渐清晰 */}
      <div className={styles.aperture} />
      {/* Logo 从中心放大 */}
      <div className={styles.logoWrap}>
        <img src="/brand/logo-mark-on-light.png" alt="" className={styles.logo} />
      </div>
      {/* 云层散开效果 */}
      <div className={styles.clouds}>
        <div className={`${styles.cloud} ${styles.cloud1}`} />
        <div className={`${styles.cloud} ${styles.cloud2}`} />
        <div className={`${styles.cloud} ${styles.cloud3}`} />
      </div>
    </div>
  )
}

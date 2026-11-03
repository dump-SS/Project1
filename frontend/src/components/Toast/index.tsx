/**
 * 轻提示。#52（product-redesign-target.md 第 828 行）要求覆盖收藏时给一句
 * 「已更新这个收藏」，否则用户会以为没生效。
 *
 * 刻意做成「受控 + 自动消失」的哑组件，不引 context / 不做全局总线：
 * 目前只有 Chat 划选收藏一处要用，等第二个调用方出现再抽公共层。
 */
import { useEffect } from 'react'
import styles from './index.module.css'

interface ToastProps {
  text: string
  onDone: () => void
  /** 自动消失毫秒数 */
  duration?: number
}

export default function Toast({ text, onDone, duration = 2200 }: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, duration)
    return () => window.clearTimeout(timer)
  }, [duration, onDone, text])

  // role=status 让读屏软件播报，视觉上不打断操作（pointer-events: none）
  return (
    <div className={styles.toast} role="status">
      {text}
    </div>
  )
}

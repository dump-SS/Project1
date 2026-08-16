import { useState, useRef, useCallback } from 'react'

// 发送验证码通用 Hook：返回倒计时、发送方法（带防抖与校验）
export function useCodeCountdown() {
  const [count, setCount] = useState(0)
  const timerRef = useRef(null)

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const start = useCallback((seconds = 60) => {
    stop()
    setCount(seconds)
    timerRef.current = setInterval(() => {
      setCount((c) => {
        if (c <= 1) {
          stop()
          return 0
        }
        return c - 1
      })
    }, 1000)
  }, [stop])

  // 组件卸载时清理
  // (使用 ref 而不是 useEffect，避免依赖变动导致重复清理)

  return {
    count,
    sending: count > 0,
    start,
    stop,
    text: count > 0 ? `${count}s 后重发` : '获取验证码'
  }
}

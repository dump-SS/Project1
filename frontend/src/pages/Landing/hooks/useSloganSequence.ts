import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'

/**
 * Hero slogan 退格编排引擎（visual-language §7.1 精确节奏）：
 * 打出「学习工具围着题转！」→ 停 1s → 退格（先快后慢）删「！」「题」
 * （删到「题」前停半秒）→ 打「你」（蓝）→「。」落下 → 光标熄灭。
 *
 * 与功能屏 TextType 的「写出」模式构成一删一写的呼应，参数刻意不同。
 * 实现：预生成事件时间线（text 快照 + 间隔），单一 timeout 链推进。
 */

const INITIAL = '学习工具围着题转！'
const AFTER_DELETE = '学习工具围着转' // 删「！」「题」后
const WITH_YOU = '学习工具围着你转' // 「你」入位（题的位置）
const FINAL = '学习工具围着你转。'

type Ev = { text: string; gapMs: number; you?: boolean }

function buildTimeline(): Ev[] {
  const evs: Ev[] = []
  // ① 逐字打出初稿（含首帧延迟）
  for (let i = 1; i <= INITIAL.length; i++) {
    evs.push({ text: INITIAL.slice(0, i), gapMs: i === 1 ? 600 : 130 })
  }
  // ② 打完停 1s
  evs.push({ text: INITIAL, gapMs: 1000 })
  // ③ 退格先快：删「！」→「学习工具围着题转」
  evs.push({ text: INITIAL.slice(0, -1), gapMs: 90 })
  // ④ 删到「题」前：半秒停顿（文本不变）
  evs.push({ text: INITIAL.slice(0, -1), gapMs: 500 })
  // ⑤ 退格后慢：删「题」→「学习工具围着转」
  evs.push({ text: AFTER_DELETE, gapMs: 300 })
  // ⑥ 打「你」（入位在「着」与「转」之间）
  evs.push({ text: WITH_YOU, gapMs: 300, you: true })
  // ⑦ 句号落下（刻意慢半拍）
  evs.push({ text: WITH_YOU, gapMs: 420 })
  evs.push({ text: FINAL, gapMs: 160, you: true })
  return evs
}

export interface SloganState {
  /** 当前显示文本 */
  text: string
  /** 「你」是否在屏上（蓝字高亮） */
  youVisible: boolean
  /** 成稿（光标熄灭） */
  finished: boolean
}

export function useSloganSequence(): SloganState {
  const reduced = useReducedMotion()
  const [state, setState] = useState<SloganState>({
    text: '',
    youVisible: false,
    finished: false,
  })
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    // reduced-motion：直接显示成稿（dev-spec §6）
    if (reduced) {
      setState({ text: FINAL, youVisible: true, finished: true })
      return
    }

    const timeline = buildTimeline()
    let cancelled = false
    let idx = 0

    const tick = () => {
      if (cancelled) return
      const ev = timeline[idx]
      if (!ev) {
        setState((s) => ({ ...s, finished: true }))
        return
      }
      setState({ text: ev.text, youVisible: ev.you ?? false, finished: false })
      idx++
      timer.current = setTimeout(tick, ev.gapMs)
    }
    tick()

    return () => {
      cancelled = true
      if (timer.current) clearTimeout(timer.current)
    }
  }, [reduced])

  return state
}

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'

/**
 * Hero slogan 退格编排引擎。
 * 2026-09-25 Skyer 调整（覆盖 visual-language §7.1 原节奏口径）：
 * 打出「学习工具，围着题转」→ 停 1s → 退格（先快后慢）退掉后四个字「围着题转」
 * → 打「围着你转」（加粗；「你」同时为蓝）→「。」落下 → 光标熄灭。
 *
 * 与功能屏 TextType 的「写出」模式构成一删一写的呼应，参数刻意不同。
 * 实现：预生成事件时间线（text 快照 + 间隔），单一 timeout 链推进。
 */

const INITIAL = '学习工具，围着题转'
const AFTER_DELETE = '学习工具，' // 退掉后四字「围着题转」
const FINAL = '学习工具，围着你转。'

type Ev = { text: string; gapMs: number; you?: boolean; strong?: boolean }

function buildTimeline(): Ev[] {
  const evs: Ev[] = []
  // ① 逐字打出初稿（含首帧延迟）
  for (let i = 1; i <= INITIAL.length; i++) {
    evs.push({ text: INITIAL.slice(0, i), gapMs: i === 1 ? 600 : 130 })
  }
  // ② 打完停 1s
  evs.push({ text: INITIAL, gapMs: 1000 })
  // ③ 退格先快：删「转」「题」
  evs.push({ text: '学习工具，围着题', gapMs: 90 })
  evs.push({ text: '学习工具，围着', gapMs: 90 })
  // ④ 删到一半：半秒停顿（保留原「先快—停—慢」节奏感）
  evs.push({ text: '学习工具，围着', gapMs: 500 })
  // ⑤ 退格后慢：删「着」「围」→ 剩「学习工具，」
  evs.push({ text: '学习工具，围', gapMs: 200 })
  evs.push({ text: AFTER_DELETE, gapMs: 300 })
  // ⑥ 打「围着你转」（新加段加粗；「你」入位即蓝）
  evs.push({ text: '学习工具，围', gapMs: 200, strong: true })
  evs.push({ text: '学习工具，围着', gapMs: 200, strong: true })
  evs.push({ text: '学习工具，围着你', gapMs: 220, strong: true, you: true })
  evs.push({ text: '学习工具，围着你转', gapMs: 300, strong: true, you: true })
  // ⑦ 句号落下（刻意慢半拍，不在加粗段内）
  evs.push({ text: '学习工具，围着你转', gapMs: 420, strong: true, you: true })
  evs.push({ text: FINAL, gapMs: 160, strong: true, you: true })
  return evs
}

export interface SloganState {
  /** 当前显示文本 */
  text: string
  /** 「你」是否在屏上（蓝字高亮） */
  youVisible: boolean
  /** 加粗段起始下标（新加的「围着你转」）；null = 当前无加粗段 */
  strongFrom: number | null
  /** 成稿（光标熄灭） */
  finished: boolean
}

export function useSloganSequence(): SloganState {
  const reduced = useReducedMotion()
  const [state, setState] = useState<SloganState>({
    text: '',
    youVisible: false,
    strongFrom: null,
    finished: false,
  })
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    // reduced-motion：直接显示成稿（dev-spec §6）
    if (reduced) {
      setState({ text: FINAL, youVisible: true, strongFrom: AFTER_DELETE.length, finished: true })
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
      setState({
        text: ev.text,
        youVisible: ev.you ?? false,
        strongFrom: ev.strong ? AFTER_DELETE.length : null,
        finished: false,
      })
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

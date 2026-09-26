import { useEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'
import type { SloganCopy } from '../content/copy'

/**
 * Hero slogan 退格编排引擎（2026-09-27 参数化以支持双语）。
 *
 * 编排（中文 2026-09-25 口径，英文同构）：
 *   打出初稿 → 停 1s → 退格（先快后慢，中途半秒停顿）退到公共前缀 base
 *   → 打「新加段」strong（加粗；命中的 highlight 片段同时为蓝）
 *   → 句末标点落下 → 光标熄灭。
 *
 * 与功能屏 TextType 的「写出」模式构成一删一写的呼应，参数刻意不同。
 * 摘要：slogan 里的 base/initial/final/strong/highlight 全由本语言的文案给出
 * （见 content/copy.zh.ts / copy.en.ts），引擎不再写死任何字。
 */

type Ev = { text: string; gapMs: number; you?: boolean; strong?: boolean }

/** 退格的节奏（先快后慢，中途停半秒）：从 initial 末尾逐字退到 base */
const DEL = { fast: 90, pause: 500, slow: 200 }
/** 打字节奏：首帧 600ms，其后逐字 130ms；新加段稍慢（200–220ms） */
const TYPE = { first: 600, char: 130, strong: 205 }

function buildTimeline(s: SloganCopy): Ev[] {
  const evs: Ev[] = []
  const { base, initial, final, strong, highlight } = s

  // ① 逐字打出初稿
  for (let i = 1; i <= initial.length; i++) {
    evs.push({ text: initial.slice(0, i), gapMs: i === 1 ? TYPE.first : TYPE.char })
  }
  // ② 打完停 1s
  evs.push({ text: initial, gapMs: 1000 })

  // ③ 退格：末尾两字快退 → 停半秒 → 其余慢退，退到 base 为止
  const delCount = Math.max(0, initial.length - base.length)
  for (let k = 0; k < delCount; k++) {
    const text = initial.slice(0, initial.length - k - 1)
    const firstTwo = k < 2
    const gapMs = firstTwo ? DEL.fast : k === 2 ? DEL.pause : DEL.slow
    evs.push({ text, gapMs })
  }

  // ④ 打新加段（加粗；highlight 打全那一刻起为蓝）
  for (let i = 1; i <= strong.length; i++) {
    const typed = strong.slice(0, i)
    evs.push({
      text: base + typed,
      gapMs: i === strong.length ? 300 : TYPE.strong,
      strong: true,
      you: typed.includes(highlight),
    })
  }

  // ⑤ 句末标点落下（刻意慢半拍，落在加粗段之外）；成稿以 final 收束
  const tail = final.slice(base.length + strong.length)
  if (tail) {
    evs.push({ text: final, gapMs: 420, strong: true, you: true })
  } else {
    evs.push({ text: final, gapMs: 160, strong: true, you: true })
  }
  evs.push({ text: final, gapMs: 160, strong: true, you: true })
  return evs
}

export interface SloganState {
  /** 当前显示文本 */
  text: string
  /** highlight 片段是否在屏上（蓝字高亮） */
  youVisible: boolean
  /** 加粗段起始下标（新加段）；null = 当前无加粗段 */
  strongFrom: number | null
  /** 成稿（光标熄灭） */
  finished: boolean
}

export function useSloganSequence(slogan: SloganCopy): SloganState {
  const reduced = useReducedMotion()
  const [state, setState] = useState<SloganState>({
    text: '',
    youVisible: false,
    strongFrom: null,
    finished: false,
  })
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const timeline = useMemo(() => buildTimeline(slogan), [slogan])

  useEffect(() => {
    // reduced-motion：直接显示成稿（dev-spec §6）
    if (reduced) {
      setState({
        text: slogan.final,
        youVisible: true,
        strongFrom: slogan.base.length,
        finished: true,
      })
      return
    }

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
        strongFrom: ev.strong ? slogan.base.length : null,
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
  }, [reduced, timeline, slogan])

  return state
}

/**
 * D23 自定义常用语：localStorage 持久化 + 内置快捷动作清单。
 *
 * 两种形态（都要）：
 * - 纯文本快捷语：一段固定文字，点击即填入/发送
 * - 固化 prompt（可带前缀）：content 以 `/xxx` 开头即带意图前缀（前缀可系统内置也可自定）
 *
 * 支持用户自定义分组：每条记录一个 group；默认「我的常用语」。
 */
import { genId, type PhraseItem } from './types'

const STORAGE_KEY = 'chat:phrases'

/** 内置快捷动作（D22：开始计时 / 搜题 / 建计划 / 建目标），点击直接发送，不入库。 */
export const BUILTIN_ACTIONS: { label: string; send: string }[] = [
  { label: '开始计时', send: '我想开始专注学习数学 25 分钟' },
  { label: '搜题', send: '/搜题' },
  { label: '制定计划', send: '/计划 帮我制定今天的复习计划' },
  { label: '设定目标', send: '/目标 我打算这周攻克函数单调性' },
]

export function readPhrases(): PhraseItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function writePhrases(list: PhraseItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // 忽略写入失败（隐私模式等）
  }
}

export function addPhrase(pick: Omit<PhraseItem, 'id'>) {
  const list = readPhrases()
  list.unshift({ ...pick, id: genId('ph') })
  writePhrases(list)
  return list
}

export function removePhrase(id: string) {
  const list = readPhrases().filter((p) => p.id !== id)
  writePhrases(list)
  return list
}

/** 从所有常用语里取出的分组名（出现顺序；空组名归入「我的常用语」） */
export function phraseGroups(list: PhraseItem[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const p of list) {
    const g = p.group || '我的常用语'
    if (!seen.has(g)) {
      seen.add(g)
      out.push(g)
    }
  }
  return out
}
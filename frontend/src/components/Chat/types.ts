/**
 * Chat 模块共享类型与 localStorage 工具。
 *
 * 错题数据与错题本页（pages/ErrorBook）共享同一套 localStorage key：
 * `errors_{subject}`（subject ∈ math / physics / english），
 * 两边读写完全一致，互相同步。
 */

export type ChatRole = 'user' | 'ai'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  createdAt: number
}

export type Subject = 'math' | 'physics' | 'english'

export type ErrorReason = 'concept' | 'calculation' | 'reading' | 'method' | 'other'

/** 与错题本页 ErrorItem 结构保持一致 */
export interface ErrorItem {
  id: string
  questionText: string
  reason: ErrorReason
  knowledgeNames: string[]
  createdAt: number
}

export const SUBJECT_LABEL: Record<Subject, string> = {
  math: '数学',
  physics: '物理',
  english: '英语',
}

export const REASON_LABEL: Record<ErrorReason, string> = {
  concept: '概念不清',
  calculation: '计算失误',
  reading: '审题',
  method: '方法不会',
  other: '其他',
}

export const REASON_OPTIONS: { value: ErrorReason; label: string }[] = [
  { value: 'concept', label: '概念不清' },
  { value: 'calculation', label: '计算失误' },
  { value: 'reading', label: '审题' },
  { value: 'method', label: '方法不会' },
  { value: 'other', label: '其他' },
]

/** 各学科可选知识点（与错题本页 SUBJECT_KNOWLEDGE 一致） */
export const SUBJECT_KNOWLEDGE: Record<Subject, string[]> = {
  math: ['函数单调性', '复合函数判定', '数列求和', '等差数列'],
  physics: ['受力分析', '运动学公式', '能量守恒', '电路欧姆定律'],
  english: ['时态辨析', '从句引导词', '词义辨析', '阅读主旨'],
}

/* ============ localStorage ============ */

export const storageKey = (s: Subject) => `errors_${s}`

export function readErrors(s: Subject): ErrorItem[] {
  try {
    const raw = localStorage.getItem(storageKey(s))
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function writeErrors(s: Subject, list: ErrorItem[]) {
  try {
    localStorage.setItem(storageKey(s), JSON.stringify(list))
  } catch {
    // 忽略写入失败（隐私模式等）
  }
}

/** 读取全部学科的错题，按时间倒序合并 */
export function readAllErrors(): (ErrorItem & { subject: Subject })[] {
  const subjects: Subject[] = ['math', 'physics', 'english']
  return subjects
    .flatMap((s) => readErrors(s).map((e) => ({ ...e, subject: s })))
    .sort((a, b) => b.createdAt - a.createdAt)
}

export const genId = (prefix: string) =>
  `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

/** 相对时间：X 秒前 / X 分钟前 / X 小时前 / X 天前 */
export function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return `${Math.max(1, Math.floor(diff / 1000))} 秒前`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

/** HH:MM 格式时间 */
export function formatTime(ts: number): string {
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

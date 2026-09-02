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

export type Subject = 'YW' | 'SX' | 'YY' | 'LS' | 'DL' | 'ZZ' | 'WL' | 'HX' | 'SW'

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
  YW: '语文',
  SX: '数学',
  YY: '英语',
  LS: '历史',
  DL: '地理',
  ZZ: '政治',
  WL: '物理',
  HX: '化学',
  SW: '生物',
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
  YW: ['文言文实词', '现代文阅读', '古诗鉴赏', '作文立意'],
  SX: ['函数单调性', '复合函数判定', '数列求和', '等差数列'],
  YY: ['时态辨析', '从句引导词', '词义辨析', '阅读主旨'],
  LS: ['中国古代政治制度', '中国近代史', '世界近现代史', '史料分析'],
  DL: ['大气环流', '洋流分布', '地形地貌', '区位因素'],
  ZZ: ['经济生活', '政治生活', '唯物辩证法', '价值规律'],
  WL: ['受力分析', '运动学公式', '能量守恒', '电路欧姆定律'],
  HX: ['化学方程式配平', '物质的量', '氧化还原反应', '离子反应'],
  SW: ['细胞结构与功能', '光合作用', '遗传规律', '生态系统'],
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
  const subjects: Subject[] = ['YW', 'SX', 'YY', 'LS', 'DL', 'ZZ', 'WL', 'HX', 'SW']
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

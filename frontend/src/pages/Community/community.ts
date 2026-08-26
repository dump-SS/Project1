/**
 * 模块三「匿名群体对比」· 纯前端数据层
 * ------------------------------------------------------------
 * 不调用任何后端接口。数据只存在浏览器 localStorage：
 *  - community_my_data：用户自己刚提交的一条记录
 *  - community_pool：模拟的群体数据池（首次访问写入 20 条预置假数据，
 *    之后用户每次提交都会 push 进池子，模拟"越来越多人参与"）
 */

export type CommunitySubject = 'SX' | 'WL' | 'YY' | 'other'

export interface CommunityRecord {
  /** 本周学习时长（小时，0-40） */
  hours: number
  /** 平均每日专注度（1-5） */
  focus: number
  /** 平均每日疲劳度（1-5） */
  fatigue: number
  /** 本周完成率（0-100） */
  completion: number
  /** 学科 */
  subject: CommunitySubject
}

export const MY_DATA_KEY = 'community_my_data'
export const POOL_KEY = 'community_pool'

/** 参与百分位对比的 4 个数值指标（学科是分组维度，不参与排名） */
export type MetricKey = 'hours' | 'focus' | 'fatigue' | 'completion'

export interface MetricMeta {
  key: MetricKey
  label: string
  shortLabel: string
  unit: string
  min: number
  max: number
  /** 直方图分桶数 */
  bins: number
}

export const METRICS: MetricMeta[] = [
  { key: 'hours', label: '本周学习时长', shortLabel: '学习时长', unit: '小时', min: 0, max: 40, bins: 8 },
  { key: 'focus', label: '平均每日专注度', shortLabel: '专注度', unit: '分', min: 1, max: 5, bins: 4 },
  { key: 'fatigue', label: '平均每日疲劳度', shortLabel: '疲劳度', unit: '分', min: 1, max: 5, bins: 4 },
  { key: 'completion', label: '本周完成率', shortLabel: '完成率', unit: '%', min: 0, max: 100, bins: 10 },
]

export const COMMUNITY_SUBJECTS: CommunitySubject[] = ['SX', 'WL', 'YY', 'other']

/**
 * 预置群体数据（20 条）。
 * 覆盖四个学科、不同数值区间，大致呈"中间多、两头少"的分布，
 * 让百分位和直方图看起来接近真实群体。
 */
const PRESET_POOL: CommunityRecord[] = [
  { hours: 22, focus: 4, fatigue: 2, completion: 85, subject: 'SX' },
  { hours: 15, focus: 3, fatigue: 3, completion: 70, subject: 'SX' },
  { hours: 28, focus: 5, fatigue: 3, completion: 92, subject: 'SX' },
  { hours: 10, focus: 2, fatigue: 4, completion: 45, subject: 'SX' },
  { hours: 18, focus: 4, fatigue: 2, completion: 78, subject: 'SX' },
  { hours: 25, focus: 4, fatigue: 3, completion: 88, subject: 'WL' },
  { hours: 12, focus: 3, fatigue: 4, completion: 55, subject: 'WL' },
  { hours: 30, focus: 5, fatigue: 4, completion: 95, subject: 'WL' },
  { hours: 8, focus: 2, fatigue: 2, completion: 40, subject: 'WL' },
  { hours: 20, focus: 3, fatigue: 3, completion: 72, subject: 'WL' },
  { hours: 16, focus: 4, fatigue: 2, completion: 80, subject: 'YY' },
  { hours: 24, focus: 3, fatigue: 3, completion: 75, subject: 'YY' },
  { hours: 6, focus: 2, fatigue: 1, completion: 30, subject: 'YY' },
  { hours: 32, focus: 5, fatigue: 4, completion: 96, subject: 'YY' },
  { hours: 14, focus: 3, fatigue: 5, completion: 60, subject: 'YY' },
  { hours: 26, focus: 4, fatigue: 3, completion: 82, subject: 'other' },
  { hours: 11, focus: 2, fatigue: 3, completion: 50, subject: 'other' },
  { hours: 19, focus: 3, fatigue: 2, completion: 68, subject: 'other' },
  { hours: 35, focus: 5, fatigue: 5, completion: 98, subject: 'other' },
  { hours: 9, focus: 1, fatigue: 2, completion: 35, subject: 'other' },
]

function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function writeJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 隐私模式等写入失败时静默降级，页面仍可用（仅本次会话内存态）
  }
}

/** 页面加载时调用：pool 不存在则写入 20 条预置假数据 */
export function ensurePool(): CommunityRecord[] {
  const existing = readJson<CommunityRecord[]>(POOL_KEY)
  if (Array.isArray(existing) && existing.length > 0) return existing
  writeJson(POOL_KEY, PRESET_POOL)
  return [...PRESET_POOL]
}

export function loadPool(): CommunityRecord[] {
  const pool = readJson<CommunityRecord[]>(POOL_KEY)
  return Array.isArray(pool) ? pool : []
}

export function loadMyData(): CommunityRecord | null {
  const data = readJson<CommunityRecord>(MY_DATA_KEY)
  return data && typeof data === 'object' ? data : null
}

/** 匿名提交：存"我的数据"，同时 push 进群体池 */
export function saveMyData(record: CommunityRecord) {
  writeJson(MY_DATA_KEY, record)
  const pool = loadPool()
  pool.push(record)
  writeJson(POOL_KEY, pool)
}

/**
 * 百分位：pool 中数值低于用户值的人数 / 总人数 × 100，取整。
 * 用户自己的记录也在 pool 里，但不会比"自己低"，只计入分母。
 */
export function percentile(pool: CommunityRecord[], key: MetricKey, value: number): number {
  if (pool.length === 0) return 0
  const below = pool.filter((r) => r[key] < value).length
  return Math.round((below / pool.length) * 100)
}

/** 直方图分桶：把 [min, max] 均分为 bins 桶，统计每桶人数 */
export function histogram(
  pool: CommunityRecord[],
  key: MetricKey,
  min: number,
  max: number,
  bins: number,
): number[] {
  const counts = new Array<number>(bins).fill(0)
  const width = (max - min) / bins
  for (const r of pool) {
    const v = Math.min(Math.max(r[key], min), max)
    let idx = Math.floor((v - min) / width)
    if (idx >= bins) idx = bins - 1 // 最大值落入最后一桶
    counts[idx] += 1
  }
  return counts
}

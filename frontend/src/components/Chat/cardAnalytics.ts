/**
 * Chat 卡片埋点（§5 #2 前端埋点接线 · D39）。
 *
 * 为什么单独一个文件：
 * - 把「埋点失败绝不影响主流程」这条保证收在一处，而不是散落在 7 个卡片组件里各写一遍 try/catch；
 * - 三个事件的发射点在这里可枚举，便于 review 与后续补埋。
 *
 * 契约与后端依据：
 * - 端点 POST /analytics/events（backend/routes/governance.py:240，路由无 prefix，
 *   经 main.py:189 include_router(governance.router) → 实际路径 /api/v1/analytics/events）
 * - category 必须是三块之一（backend/schemas/governance.py:58 AnalyticsCategory），
 *   写错会被 track_event 丢弃 → 端点返回 400。本文件用字面量 'chat_interaction'，与该枚举一致。
 * - eventType 契约上是 type: string / maxLength: 64（非 enum），
 *   描述里列了 card_shown / card_clicked / intent_corrected 等 9 个名（openapi.yaml:5978）。
 *
 * ⚠️ payload 为什么不带卡片标题：
 * 契约要求本表「只收结构化事件体、不含对话原文流水」（openapi.yaml:5967-5969, 6477-6480）。
 * card.title 上限 60 字，但它可能是用户自己写的目标名（如「今天背完 50 个单词」），
 * 那属于用户内容而不是结构化字段。埋点只需要「哪一类卡片、哪个动作、点了哪个按钮」
 * 就够算 §1.1 首日闭环与 §1.2 卡片点击率，所以这里只送结构化字段，**不送 title**。
 */
import { postAnalyticsEvent } from '@/services/feedback'
import type { ChatCard } from './types'

/** 卡片动作键（从 payload.action 取；缺省时由 type 推导） */
export type CardClickButton =
  | 'start_study'
  | 'create_goal'
  | 'delete_goal'
  | 'view_knowledge'
  | 'worksheet_confirm'
  | 'dismiss'

/** 送库的 payload 形状——刻意保持「结构化、可枚举、不含用户文本」 */
export interface CardEventPayload extends Record<string, unknown> {
  cardType: string
  action?: string
  button?: CardClickButton
}

function pickAction(card: ChatCard): string | undefined {
  const action = card.payload?.action
  return typeof action === 'string' && action ? action : undefined
}

function buildPayload(card: ChatCard, extra?: Partial<CardEventPayload>): CardEventPayload {
  const action = pickAction(card)
  const payload: CardEventPayload = { cardType: typeof card.type === 'string' ? card.type : 'unknown' }
  if (action) payload.action = action
  return { ...payload, ...extra }
}

/**
 * 上报一条卡片事件。
 *
 * 契约级保证：fire-and-forget。这里刻意 **不 await**、**不 rethrow**——
 * 埋点是观测手段，用户点卡片失败了绝不能因为埋点也失败而崩（lead-1 派活硬性边界）。
 * 失败只在这里被吞掉，不冒泡到调用方。
 */
function fire(eventType: 'card_shown' | 'card_clicked', payload: CardEventPayload): void {
  try {
    const p = postAnalyticsEvent({ category: 'chat_interaction', eventType, payload })
    // postAnalyticsEvent 走 apiPost，返回 Promise；挂 .catch 断掉 rejection
    if (p && typeof p.catch === 'function') p.catch(() => {})
  } catch {
    // 极端情况（如 service 初始化抛错）同样吞掉：埋点永远不阻断主流程
  }
}

/** 卡片曝光：渲染即上报，每次挂载一次（由 CardExposure 的 ref 保证不重复） */
export function trackCardShown(card: ChatCard): void {
  fire('card_shown', buildPayload(card))
}

/** 卡片点击：用户点了卡片上的动作按钮 */
export function trackCardClicked(card: ChatCard, button: CardClickButton): void {
  fire('card_clicked', buildPayload(card, { button }))
}

export const __testing = { buildPayload }

/**
 * 首页推荐卡 service（D21/D28，契约 v1.21.0）。
 *
 * 形状已核过契约，别猜：
 * - GET /me/home-cards 返回**数组** HomeCardGroupResult[]（不是 {groups:[...]} 包装）；
 *   组顺序后端保证 Go on → 推荐 → 洞察，空组不返回。
 * - POST /me/card-impressions 请求体 **camelCase**：group / cardType / fingerprint / action，
 *   shownAt 可省略（服务端记请求时刻）。后端 CardImpressionCreate 用 alias="cardType"，
 *   传 card_type 会被丢。
 * - fingerprint 由后端产卡时算好、随卡下发，前端**原样回填**，不在前端重算（规则真源在后端）。
 */
import { apiGet, apiPost } from './http'

export type HomeCardGroup = 'go_on' | 'recommend' | 'insight'

export type HomeCardType =
  | 'continue_plan'
  | 'state_advice'
  | 'content_advice'
  | 'goal_planning'
  | 'group_insight'

export type CardAction = 'shown' | 'clicked' | 'dismissed'

/** type 的文字标签（#51 视觉未拍板前用文字区分， charter §五） */
export const HOME_CARD_TYPE_LABEL: Record<HomeCardType, string> = {
  continue_plan: '继续计划',
  state_advice: '状态建议',
  content_advice: '内容建议',
  goal_planning: '目标规划',
  group_insight: '群体洞察',
}

export const HOME_CARD_GROUP_LABEL: Record<HomeCardGroup, string> = {
  go_on: 'Go on',
  recommend: '推荐',
  insight: '洞察',
}

export interface HomeCardPayload {
  refs?: Record<string, unknown> | null
  generated?: Record<string, unknown> | null
  instruction?: string | null
}

export interface HomeCard {
  type: HomeCardType
  display: { title: string; subtitle?: string | null }
  payload?: HomeCardPayload | null
  fingerprint: string
}

export interface HomeCardGroupResult {
  group: HomeCardGroup
  cards: HomeCard[]
}

export interface CardImpressionInput {
  group: HomeCardGroup
  cardType: HomeCardType
  fingerprint: string
  action: CardAction
  /** 省略时服务端以收到请求时刻为事件时间 */
  shownAt?: string
}

export interface CardImpressionOut {
  id: string
  createdAt: string
}

export function getHomeCards(signal?: AbortSignal): Promise<HomeCardGroupResult[]> {
  return apiGet('/me/home-cards', undefined, signal)
}

export function reportCardImpression(
  input: CardImpressionInput,
  signal?: AbortSignal,
): Promise<CardImpressionOut> {
  return apiPost('/me/card-impressions', input, signal)
}

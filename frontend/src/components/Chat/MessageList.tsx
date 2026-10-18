/**
 * 消息列表：上下滚动容器，新消息 / 正在输入 状态变化时自动滚到底部。
 */

import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import type { ChatMessage } from './types'

interface MessageListProps {
  messages: ChatMessage[]
  /** AI「正在输入…」三点动画 */
  typing: boolean
  /**
   * 「处理中」补充说明（契约 v1.13.0 带图异步）。
   *
   * 为什么单独一个 prop 而不是把文案塞进三点动画：`.chat-typing span` 的 CSS 是
   * 给每个 span 固定 7px 圆点，文字塞进去会被压成三个小方块。所以这里**另起一个气泡**。
   * 不传时行为与从前完全一致。
   */
  pendingHint?: string | null
}

export default function MessageList({ messages, typing, pendingHint }: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = listRef.current
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, typing])

  return (
    <div className="chat-list" ref={listRef}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      {/* 处理中说明：带图推理可能跑几分钟，只给三点动画用户会以为卡死 */}
      {typing && pendingHint && (
        <div className="chat-msg-row chat-msg-ai">
          <div className="chat-avatar" aria-hidden="true">
            AI
          </div>
          <div className="chat-bubble chat-bubble-ai glass" role="status">
            {pendingHint}
          </div>
        </div>
      )}
      {typing && (
        <div className="chat-msg-row chat-msg-ai">
          <div className="chat-avatar" aria-hidden="true">
            AI
          </div>
          <div className="chat-bubble chat-bubble-ai glass chat-typing" aria-label="正在输入">
            <span />
            <span />
            <span />
          </div>
        </div>
      )}
    </div>
  )
}

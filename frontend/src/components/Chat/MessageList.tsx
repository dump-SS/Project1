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
}

export default function MessageList({ messages, typing }: MessageListProps) {
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

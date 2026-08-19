/**
 * 消息气泡：用户右对齐（纯色蓝），AI 左对齐（液态玻璃 + markdown 渲染）。
 */

import ReactMarkdown from 'react-markdown'
import { formatTime, type ChatMessage } from './types'

interface MessageBubbleProps {
  message: ChatMessage
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  return (
    <div className={`chat-msg-row ${isUser ? 'chat-msg-user' : 'chat-msg-ai'}`}>
      {!isUser && (
        <div className="chat-avatar" aria-hidden="true">
          AI
        </div>
      )}
      <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-ai glass'}`}>
        {isUser ? (
          <span className="chat-bubble-text">{message.content}</span>
        ) : (
          <div className="chat-md">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
        <span className="chat-bubble-time">{formatTime(message.createdAt)}</span>
      </div>
    </div>
  )
}

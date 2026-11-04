/**
 * 消息气泡：用户右对齐（纯色蓝），AI 左对齐（液态玻璃 + markdown 渲染）。
 * AI 气泡带「收藏」按钮（§4.8.1 第 797 行：任何模型输出都可一键收藏）——
 * 收藏存的是 markdown 快照 + 保存时算好的渲染↔原文映射（方案 C）。
 */

import ReactMarkdown from 'react-markdown'
import ChatCards from './ChatCards'
import { formatTime, type ChatMessage } from './types'

interface MessageBubbleProps {
  message: ChatMessage
  /** 不传则不渲染收藏按钮（保持纯展示用法） */
  onCollect?: (message: ChatMessage) => void
}

export default function MessageBubble({ message, onCollect }: MessageBubbleProps) {
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
        {!isUser && <ChatCards cards={message.cards || []} />}
        <div className="chat-bubble-foot">
          {!isUser && onCollect && (
            <button
              type="button"
              className="chat-collect-btn"
              onClick={() => onCollect(message)}
              title="收藏这条回复（存一份快照，原文过期也照样能读）"
            >
              收藏
            </button>
          )}
          <span className="chat-bubble-time">{formatTime(message.createdAt)}</span>
        </div>
      </div>
    </div>
  )
}

/**
 * AI 辅导页 · 板块二核心交互页（纯前端演示，无后端）。
 *
 * 三栏布局：
 * - 左侧 300px：快速引用（我的错题 / 知识点速查 / 快捷提问）
 * - 中间：消息列表 + 底部固定输入框
 * - 右侧 280px：录入新错题 + 最近录入记录
 *
 * AI 回复全部由 setTimeout + 关键词匹配 mock（见 mockData.ts），
 * 错题数据与错题本页共享 localStorage（errors_{subject}）。
 *
 * 日夜双模式：页面头部提供太阳/月亮切换，复用全局 ThemeContext
 * （localStorage 持久化 + 全站 600ms 平滑过渡，与边栏底部按钮同源）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import MessageList from '@/components/Chat/MessageList'
import InputArea from '@/components/Chat/InputArea'
import ReferencePanel from '@/components/Chat/ReferencePanel'
import ErrorEntryPanel from '@/components/Chat/ErrorEntryPanel'
import {
  genId,
  type ChatMessage,
  type ErrorItem,
  type Subject,
} from '@/components/Chat/types'
import { useTheme } from '../../context/ThemeContext.jsx'
import { WELCOME_MESSAGE, pickMockReply } from './mockData'
import '@/components/Chat/chat.css'
import './index.css'

const AI_REPLY_DELAY = 1500

export default function ChatPage() {
  const { theme, toggleTheme } = useTheme()

  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: genId('msg'), role: 'ai', content: WELCOME_MESSAGE, createdAt: Date.now() },
  ])
  const [draft, setDraft] = useState('')
  const [typing, setTyping] = useState(false)
  /** 录入错题后 +1，通知左侧错题列表重读 localStorage */
  const [refreshKey, setRefreshKey] = useState(0)
  /** 窄屏下右侧面板改为浮层 */
  const [entryOpen, setEntryOpen] = useState(false)

  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const timerRef = useRef<number | null>(null)

  // 卸载时清理未完成的 AI 回复定时器
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    }
  }, [])

  /** 发送一条用户消息，1.5s 后追加 mock AI 回复 */
  const sendMessage = useCallback(
    (raw: string) => {
      const content = raw.trim()
      if (!content || typing) return
      setMessages((prev) => [
        ...prev,
        { id: genId('msg'), role: 'user', content, createdAt: Date.now() },
      ])
      setDraft('')
      setTyping(true)
      timerRef.current = window.setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { id: genId('msg'), role: 'ai', content: pickMockReply(content), createdAt: Date.now() },
        ])
        setTyping(false)
        timerRef.current = null
      }, AI_REPLY_DELAY)
    },
    [typing],
  )

  /** 左侧引用：填入输入框并聚焦 */
  const fillInput = useCallback((text: string) => {
    setDraft(text)
    // 等 textarea 值更新后再聚焦并自适应高度
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) {
        el.focus()
        el.style.height = 'auto'
        el.style.height = `${Math.min(el.scrollHeight, 132)}px`
      }
    })
  }, [])

  /** 录入错题保存后：刷新左侧列表 + 自动发一条用户消息（走正常 mock 回复流程） */
  const handleErrorSaved = useCallback(
    (item: ErrorItem, _subject: Subject) => {
      setRefreshKey((k) => k + 1)
      const short =
        item.questionText.length > 30 ? `${item.questionText.slice(0, 30)}…` : item.questionText
      sendMessage(`我刚录入了一道新错题：${short}，帮我分析一下`)
    },
    [sendMessage],
  )

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="chat-page">
        <header className="chat-header">
          <h1 className="chat-title">
            AI 辅导
            <span className="chat-title-en">AI Tutor</span>
          </h1>
          <div className="chat-header-actions">
            {/* 窄屏：右侧面板改浮层 */}
            <button
              type="button"
              className="chat-header-btn chat-entry-open"
              onClick={() => setEntryOpen(true)}
            >
              录入错题
            </button>
            {/* 日/夜切换（复用全局 ThemeContext） */}
            <button
              type="button"
              className="chat-header-btn"
              onClick={toggleTheme}
              aria-label={theme === 'day' ? '切换到夜间模式' : '切换到日间模式'}
              title={theme === 'day' ? '切换到夜间模式' : '切换到日间模式'}
            >
              {theme === 'day' ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" fill="currentColor" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" />
                </svg>
              )}
            </button>
          </div>
        </header>

        <div className="chat-layout">
          {/* 左侧：快速引用 */}
          <aside className="chat-left glass">
            <ReferencePanel
              onFillInput={fillInput}
              onSendQuick={sendMessage}
              refreshKey={refreshKey}
            />
          </aside>

          {/* 中间：聊天主区域 */}
          <section className="chat-center glass">
            <MessageList messages={messages} typing={typing} />
            <InputArea
              value={draft}
              onChange={setDraft}
              onSend={() => sendMessage(draft)}
              disabled={typing}
              inputRef={inputRef}
              renderQuickPanel={(close) => (
                <ReferencePanel
                  compact
                  onFillInput={fillInput}
                  onSendQuick={sendMessage}
                  refreshKey={refreshKey}
                  onPicked={close}
                />
              )}
            />
          </section>

          {/* 右侧：录入新错题 */}
          <aside className="chat-right glass">
            <ErrorEntryPanel onSaved={handleErrorSaved} />
          </aside>
        </div>

        {/* 窄屏：录入错题浮层 */}
        {entryOpen && (
          <>
            <div className="chat-entry-mask" onClick={() => setEntryOpen(false)} aria-hidden="true" />
            <div className="chat-entry-pop glass">
              <div className="chat-entry-pop-head">
                <span>录入新错题</span>
                <button type="button" onClick={() => setEntryOpen(false)} aria-label="关闭">
                  ×
                </button>
              </div>
              <ErrorEntryPanel
                onSaved={(item, subject) => {
                  handleErrorSaved(item, subject)
                  setEntryOpen(false)
                }}
              />
            </div>
          </>
        )}
      </main>
    </>
  )
}

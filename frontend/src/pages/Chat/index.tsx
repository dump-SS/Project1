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
import SelectionToolbar from '@/components/Chat/SelectionToolbar'
import FloatChat from '@/components/Chat/FloatChat'
import {
  genId,
  type ChatMessage,
  type ErrorItem,
  type RefChip,
  type Subject,
} from '@/components/Chat/types'
import { useTheme } from '../../context/ThemeContext.jsx'
import { WELCOME_MESSAGE } from './mockData'
import '@/components/Chat/chat.css'
import './index.css'

export default function ChatPage() {
  const { theme, toggleTheme } = useTheme()

  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: genId('msg'), role: 'ai', content: WELCOME_MESSAGE, createdAt: Date.now() },
  ])

  // #34：回到 AI 页先拉问候语（冷启动会带上次话题摘要），成功则用它替换初始骨架
  useEffect(() => {
    let cancelled = false
    fetch('/api/v1/chat/greeting')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data || !data.greeting || data.showGreeting === false) return
        setMessages((prev) =>
          prev.length && prev[0].role === 'ai' && prev[0].content === WELCOME_MESSAGE
            ? [{ ...prev[0], content: data.greeting }]
            : prev,
        )
      })
      .catch(() => {
        // 后端未就绪/未鉴权：保留 WELCOME_MESSAGE 兜底，不白屏
      })
    return () => {
      cancelled = true
    }
  }, [])
  const [draft, setDraft] = useState('')
  const [typing, setTyping] = useState(false)
  /** 录入错题后 +1，通知左侧错题列表重读 localStorage */
  const [refreshKey, setRefreshKey] = useState(0)
  /** 窄屏下右侧面板改为浮层 */
  const [entryOpen, setEntryOpen] = useState(false)

  // ---- D51 划选 / 引用块 / 随手问浮窗 ----
  const [sel, setSel] = useState<{ x: number; y: number; text: string } | null>(null)
  const [refs, setRefs] = useState<RefChip[]>([])
  const [floatOpen, setFloatOpen] = useState(false)
  const [floatInit, setFloatInit] = useState('')

  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  // 全局划选：在对话区内选中文本 → 浮出工具条（引用主对话 / 随手问）
  useEffect(() => {
    const onMouseUp = () => {
      const selection = window.getSelection()
      if (!selection || selection.isCollapsed) return setSel(null)
      const anchor = selection.anchorNode as Node | null
      const host = anchor && anchor.nodeType === Node.TEXT_NODE ? anchor.parentNode : anchor
      if (!host || !(host instanceof Element) || !host.closest('.chat-page')) return setSel(null)
      const text = selection.toString().trim()
      if (!text) return setSel(null)
      const rect = selection.getRangeAt(0).getBoundingClientRect()
      setSel({ x: rect.left + window.scrollX, y: rect.top - 44 + window.scrollY, text })
    }
    const onDown = () => setTimeout(() => setSel(null), 0)
    document.addEventListener('mouseup', onMouseUp)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('mouseup', onMouseUp)
      document.removeEventListener('mousedown', onDown)
    }
  }, [])

  const addQuoteRef = (text: string) =>
    setRefs((prev) => [...prev, { id: genId('ref'), label: '引用', text }])
  const addFloatRef = (text: string) =>
    setRefs((prev) => [...prev, { id: genId('ref'), label: '浮窗对话', text }])
  const removeRef = (id: string) => setRefs((prev) => prev.filter((r) => r.id !== id))

  // D51 主路径：引用块的正文随消息原文一起发出（让后端看到被引用内容）
  const composeWithRefs = (draft: string, refsList: RefChip[]) =>
    refsList
      .map((r) => `[${r.label}] ${r.text}`)
      .concat(draft.trim())
      .filter((s) => s)
      .join('\n')

  /** 发送一条用户消息，调用后端 /api/v1/chat 拿真实回复 */
  const sendMessage = useCallback(
    async (raw: string) => {
      const content = raw.trim()
      if (!content || typing) return
      setMessages((prev) => [
        ...prev,
        { id: genId('msg'), role: 'user', content, createdAt: Date.now() },
      ])
      setDraft('')
      setTyping(true)
      try {
        const resp = await fetch('/api/v1/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        })
        if (!resp.ok) throw new Error(`chat ${resp.status}`)
        const data = await resp.json()
        const reply = (data && data.reply) || '（未收到回复）'
        const cards = Array.isArray(data?.cards) ? data.cards : []
        setMessages((prev) => [
          ...prev,
          { id: genId('msg'), role: 'ai', content: reply, cards, createdAt: Date.now() },
        ])
      } catch (err) {
        console.error('[chat] request failed', err)
        setMessages((prev) => [
          ...prev,
          { id: genId('msg'), role: 'ai', content: '我暂时接不上你的话，能换个说法再跟我说一次吗？', createdAt: Date.now() },
        ])
      } finally {
        setTyping(false)
      }
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
              className="chat-header-btn"
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
          {/* 聊天主区域（快速引用收进输入框「+」浮层，不再常驻左栏） */}
          <section className="chat-center glass">
            <MessageList messages={messages} typing={typing} />
            <InputArea
              value={draft}
              onChange={setDraft}
              onSend={() => {
                if (!draft.trim() && refs.length === 0) return
                sendMessage(composeWithRefs(draft, refs))
                setRefs([])
              }}
              disabled={typing}
              inputRef={inputRef}
              refs={refs}
              onRemoveRef={removeRef}
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
        </div>

        {/* D51 划选工具条（引用主对话 / 随手问） */}
        {sel && (
          <SelectionToolbar
            x={sel.x}
            y={sel.y}
            text={sel.text}
            onQuote={addQuoteRef}
            onFloat={(text) => {
              setFloatInit(text)
              setFloatOpen(true)
            }}
            onDone={() => setSel(null)}
          />
        )}

        {/* D51 随手问浮窗（受限 Chat 基础问答） */}
        {floatOpen && (
          <FloatChat
            initialText={floatInit}
            onAddToMain={addFloatRef}
            onClose={() => setFloatOpen(false)}
          />
        )}

        {/* 录入错题浮层 */}
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

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
import { startTextPendingHint } from '@/components/Chat/pendingHint'
import MediaCapturePanel from '@/components/MediaCapturePanel'
import type { FCard, MediaUploadResult } from '@/services/fMedia'
import {
  ChatJobAbortedError,
  ChatJobTimeoutError,
  pollChatJob,
  sendMediaChat,
} from '@/services/chat'
import { ApiError } from '@/services/http'
import {
  genId,
  type ChatMessage,
  type ErrorItem,
  type RefChip,
  type Subject,
} from '@/components/Chat/types'
import { useTheme } from '../../context/ThemeContext.jsx'
import { takePendingToolRef, TOOL_REF_EVENT } from '@/hooks/toolRefBus'
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
  /** 带图异步提问时的「处理中」提示文案；null = 走的是同步路径，不显示 */
  const [pendingHint, setPendingHint] = useState<string | null>(null)
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

  // D57 科学计算器「添加到对话」（§4.10.3 第 873-875 行）：计算器在 AppShell 层任意页面
  // 可开，「添加」= toolRefBus 递引用 + 切至本页。挂载时取一次（覆盖刚切页的时序），
  // 再监听事件（覆盖「已在 /chat 直接添加」的时序）；take 即清空，不残留。
  useEffect(() => {
    const consume = () => {
      const payload = takePendingToolRef()
      if (payload) {
        setRefs((prev) => [
          ...prev,
          { id: genId('ref'), label: payload.label, text: payload.text, source: payload.source },
        ])
      }
    }
    consume()
    window.addEventListener(TOOL_REF_EVENT, consume)
    return () => window.removeEventListener(TOOL_REF_EVENT, consume)
  }, [])

  /**
   * F 板块：上传成功 → 把媒体 key 垫成引用块（§3.1 的 file_summary 就是同构的 ChatCard）。
   *
   * ## media chip 现在是**真图**，不再只是文字
   *
   * 后端 `ChatMessageRequest.mediaKey`（契约 v1.12.0）已支持多模态：按 key 从 R2
   * 取回字节送给模型。所以带图提问现在走 `POST /chat/media` 异步路径，
   * **真正的图片会进模型**，media chip 不再被拼成 `[题目图片] key` 文字。
   *
   * ⚠️ 这段注释曾经写着"AI 目前看不到图片内容"——那是 v1.12.0 之前的状态，
   * 留着会误导下一个人以为带图只是装饰。**别再照着旧注释理解这条链路。**
   *
   * `source: 'f_media'` 是协议里的来源标记字段，供后续收藏/讲解打标（见 RefChip 注释）。
   */
  const addMediaRef = (result: MediaUploadResult) =>
    setRefs((prev) => [
      ...prev,
      { id: genId('ref'), label: '题目图片', text: result.key, source: 'f_media' },
    ])
  /** 清除图片时把对应引用块一起撤掉，避免栈里留孤儿 chip */
  const removeMediaRef = (key: string) =>
    setRefs((prev) => prev.filter((r) => !(r.source === 'f_media' && r.text === key)))

  const handleMediaCard = useCallback((_card: FCard, result: MediaUploadResult) => {
    addMediaRef(result)
  }, [])

  // D51 主路径：引用块的正文随消息原文一起发出（让后端看到被引用内容）
  const composeWithRefs = (draft: string, refsList: RefChip[]) =>
    refsList
      .map((r) => `[${r.label}] ${r.text}`)
      .concat(draft.trim())
      .filter((s) => s)
      .join('\n')

  /**
   * 带图异步路径用：**剔除媒体 chip** 只拼文本引用。
   *
   * 为什么不能沿用 composeWithRefs：那条会把 `[题目图片] user/x/a.png` 拼进正文，
   * 而异步路径是把图片**真正按 mediaKey 送进模型的**。两者叠加会让模型既看到图、
   * 又看到一行"这里有个 key"的文字，纯属噪声。
   */
  const composeWithoutMedia = (draft: string, refsList: RefChip[]) =>
    composeWithRefs(draft, refsList.filter((r) => r.source !== 'f_media'))

  /**
   * 「处理中」提示。
   *
   * 带图推理实测中位 105.7s、最大 245.8s，三点动画干转四分钟用户会以为卡死。
   * 直接把预期耗时说清楚，比让用户猜要好。
   */
  const MEDIA_PENDING_HINT = '正在看图回答 · 带图通常要 1~4 分钟，可以先去做别的'

  /** 在途的带图任务，用于组件卸载时中止轮询（否则关页面后仍在打接口） */
  const mediaAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      mediaAbortRef.current?.abort()
    }
  }, [])

  /**
   * 发送一条用户消息，调用后端 /api/v1/chat 拿真实回复
   *
   * ## 两条路径（契约 v1.13.0）
   *
   * - **无 mediaKey → 同步**：走下面那段 fetch，**与本轮改动前逐字相同**。
   * - **有 mediaKey → 异步**：`POST /chat/media` 入队拿 jobId，再轮询
   *   `GET /chat/jobs/{jobId}`。
   *
   * 之所以分流而不是给 `/chat` 加个 async 参数：纯文本 tokens_out 只有 5~107，
   * 延迟远低于带图。为了带图的慢把整个 Chat 改异步，会让绝大多数对话体验变差
   * 还要大改前端。带图是少数派路径，就该走少数派的端点。
   */
  const sendMessage = useCallback(
    async (raw: string, mediaKey?: string) => {
      const content = raw.trim()
      if (!content || typing) return
      setMessages((prev) => [
        ...prev,
        { id: genId('msg'), role: 'user', content, createdAt: Date.now() },
      ])
      setDraft('')
      setTyping(true)

      // ---- 带图：异步路径 ----
      if (mediaKey) {
        const controller = new AbortController()
        mediaAbortRef.current = controller
        setPendingHint(MEDIA_PENDING_HINT)
        try {
          const accepted = await sendMediaChat({ content, mediaKey }, controller.signal)
          // pollAfterMs 由服务端下发，这里原样透传，不在前端写死间隔
          const job = await pollChatJob(accepted.jobId, {
            pollAfterMs: accepted.pollAfterMs,
            signal: controller.signal,
          })

          if (job.status === 'done') {
            const cards = Array.isArray(job.cards) ? job.cards : []
            setMessages((prev) => [
              ...prev,
              {
                id: genId('msg'),
                role: 'ai',
                content: job.reply || '（未收到回复）',
                cards,
                createdAt: Date.now(),
              },
            ])
          } else {
            // failed 也是**正常返回**，不是异常：契约要求用户能看到失败原因，
            // 所以这里展示 errorMessage，而不是笼统的"出错了"。
            setMessages((prev) => [
              ...prev,
              {
                id: genId('msg'),
                role: 'ai',
                content: job.errorMessage || '这次没答上来，请再发一次。',
                createdAt: Date.now(),
              },
            ])
          }
        } catch (err) {
          // 组件卸载导致的中止**不是错误**，别给用户弹失败提示
          if (!(err instanceof ChatJobAbortedError)) {
            console.error('[chat] media job failed', err)
            const text =
              err instanceof ChatJobTimeoutError
                ? '这次等得太久了，我先停下了。你可以直接再发一次。'
                : err instanceof ApiError
                  ? err.message
                  : '这次带图提问没跑完，请再发一次。'
            setMessages((prev) => [
              ...prev,
              { id: genId('msg'), role: 'ai', content: text, createdAt: Date.now() },
            ])
          }
        } finally {
          if (mediaAbortRef.current === controller) mediaAbortRef.current = null
          // 被中止 = 组件已卸载，此时不再 setState
          if (!controller.signal.aborted) {
            setPendingHint(null)
            setTyping(false)
          }
        }
        return
      }

      // ↓↓↓ 以下为**纯文本同步路径**，本轮改动**逐字未动**（diff 里只会是上下文行）↓↓↓
      // ⚠️ 唯一新增：给纯文本也接上「在等」的预期提示（复用带图那套 pendingHint 机制）。
      //    短问答是秒级，两档阈值都够不到，观感与从前完全一致；
      //    长解释（实测 66s）才会升级文案。**请求与响应处理一行未改。**
      const stopTextHint = startTextPendingHint(setPendingHint)
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
        // 清掉提示定时器 + 清掉提示文案：响应已到就不该再弹「在等」了。
        // （文案也要清，否则下一次请求会残留上一条提示）
        stopTextHint()
        setPendingHint(null)
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
            <MessageList messages={messages} typing={typing} pendingHint={pendingHint} />
            <InputArea
              value={draft}
              onChange={setDraft}
              onSend={() => {
                if (!draft.trim() && refs.length === 0) return
                // 媒体 chip 走异步、文本 chip 走同步，这里只负责分流
                const mediaRefs = refs.filter((r) => r.source === 'f_media')
                if (mediaRefs.length > 1) {
                  // 契约 ChatMediaJobRequest 只收**一个** mediaKey。多图时
                  // 明确拒绝并说明，绝不静默丢图——用户刚拍的照片被悄悄吞掉
                  // 是最糟的失败方式（与后端并发上限 429 同一口径）。
                  setMessages((prev) => [
                    ...prev,
                    {
                      id: genId('msg'),
                      role: 'ai',
                      content: '一次只能看一张题图，请先把多余的图片删掉再问。',
                      createdAt: Date.now(),
                    },
                  ])
                  return
                }
                const mediaKey = mediaRefs[0]?.text
                sendMessage(
                  mediaKey ? composeWithoutMedia(draft, refs) : composeWithRefs(draft, refs),
                  mediaKey,
                )
                setRefs([])
              }}
              disabled={typing}
              inputRef={inputRef}
              refs={refs}
              onRemoveRef={removeRef}
              renderMediaCapture={() => (
                <MediaCapturePanel
                  compact
                  onCard={handleMediaCard}
                  onClear={(key) => removeMediaRef(key)}
                />
              )}
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

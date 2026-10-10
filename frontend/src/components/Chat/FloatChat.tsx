/**
 * 随手问浮窗（D51 旁路 · 受限 Chat 基础问答）。
 *
 * 关键性质（对齐契约 §3.9.1）：
 * - 单向继承主对话背景：每次请求走 /chat?ephemeral=true，后端注入主对话上下文但不回流
 * - 浮窗内多轮：把浮窗内前几轮经 floatContext 传回，实现连续追问
 * - 不递归：不从这里再派发新浮窗
 * - 结束会话：禁止输入（不关闭），按钮变为「添加到主对话」
 * - 添加到主对话：只带显式 Q&A（可见轮次），以引用块置入主输入框，浮窗销毁
 * - 可拖动（标题栏拖拽）
 */
import { useRef, useState } from 'react'
import { genId, type FloatMsg } from './types'

interface FloatChatProps {
  /** 划选预填的首条问题 */
  initialText: string
  onAddToMain: (text: string) => void
  onClose: () => void
  /** 独立模式（C 计时页随手问）：没有「结束会话/添加到主对话」，只做 Q&A，不打断专注 */
  standalone?: boolean
}

function composeFloat(start: string, msgs: FloatMsg[]): string {
  const lines: string[] = [`随手问：`, start || '']
  for (const m of msgs) {
    lines.push(`${m.role === 'user' ? '我' : 'AI'}：${m.content}`)
  }
  return lines.filter((s) => s && s.trim()).join('\n')
}

export default function FloatChat({ initialText, onAddToMain, onClose, standalone }: FloatChatProps) {
  const [msgs, setMsgs] = useState<FloatMsg[]>([])
  const [draft, setDraft] = useState('')
  const [typing, setTyping] = useState(false)
  const [ended, setEnded] = useState(false)
  const [pos, setPos] = useState({ x: 120, y: 90 })
  const drag = useRef<{ dx: number; dy: number } | null>(null)

  const send = async (raw?: string) => {
    const content = (raw ?? draft).trim()
    if (!content || typing || ended) return
    setDraft('')
    setTyping(true)
    const userMsg: FloatMsg = { id: genId('fm'), role: 'user', content }
    setMsgs((prev) => [...prev, userMsg])
    try {
      const resp = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          ephemeral: true,
          floatContext: msgs.map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content })),
        }),
      })
      if (!resp.ok) throw new Error(`float ${resp.status}`)
      const data = await resp.json()
      const reply = (data && data.reply) || '（未收到回复）'
      setMsgs((prev) => [...prev, { id: genId('fm'), role: 'ai', content: reply }])
    } catch (err) {
      console.error('[float] request failed', err)
      setMsgs((prev) => [
        ...prev,
        { id: genId('fm'), role: 'ai', content: '我暂时接不上你的话，换个说法再问一次好吗？' },
      ])
    } finally {
      setTyping(false)
    }
  }

  const onHeaderDown = (e: React.PointerEvent) => {
    drag.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }
  const onHeaderMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    setPos({ x: e.clientX - drag.current.dx, y: e.clientY - drag.current.dy })
  }
  const onHeaderUp = () => {
    drag.current = null
  }

  return (
    <div className="chat-float" style={{ left: pos.x, top: pos.y }}>
      <header
        className="chat-float-head"
        onPointerDown={onHeaderDown}
        onPointerMove={onHeaderMove}
        onPointerUp={onHeaderUp}
      >
        <span className="chat-float-title">随手问</span>
        <button type="button" className="chat-float-close" onClick={onClose} aria-label="关闭随手问">
          ×
        </button>
      </header>

      {/* 显式输入输出（多轮追问） */}
      <div className="chat-float-body">
        {initialText && msgs.length === 0 && (
          <div className="chat-float-user">{initialText}</div>
        )}
        {msgs.map((m) => (
          <div key={m.id} className={`chat-float-msg ${m.role === 'user' ? 'chat-float-user' : 'chat-float-ai'}`}>
            {m.content}
          </div>
        ))}
        {typing && <div className="chat-float-ai chat-float-typing">…</div>}
      </div>

      <footer className="chat-float-foot">
        {!ended ? (
          <>
            <input
              className="chat-float-input"
              value={draft}
              placeholder="这里只做基础问答，不会影响主对话"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !typing) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <button type="button" className="chat-float-send" onClick={() => send()} disabled={typing || !draft.trim()}>
              问
            </button>
            {!standalone && (
              <button type="button" className="chat-float-end" onClick={() => setEnded(true)}>
                结束会话
              </button>
            )}
          </>
        ) : (
          <button type="button" className="chat-float-main" onClick={() => onAddToMain(composeFloat(initialText, msgs))}>
            添加到主对话
          </button>
        )}
      </footer>
    </div>
  )
}
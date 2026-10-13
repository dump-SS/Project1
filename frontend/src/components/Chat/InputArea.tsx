/**
 * 输入区（底部固定）：
 * - 左侧「+」按钮弹出快捷引用浮层（ReferencePanel 精简版）
 * - 中间多行文本框：Enter 发送，Shift+Enter 换行，高度自适应（上限 5 行）
 * - 右侧发送按钮
 */

import { useState, type KeyboardEvent, type MutableRefObject, type ReactNode } from 'react'
import type { RefChip } from './types'
import ReferenceChips from './ReferenceChips'

interface InputAreaProps {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  /** AI 正在输入时禁止发送 */
  disabled?: boolean
  inputRef: MutableRefObject<HTMLTextAreaElement | null>
  /** 「+」浮层内容（ReferencePanel 精简版）；浮层内点击后应调用 onQuickDone 关闭 */
  renderQuickPanel: (close: () => void) => ReactNode
  /** 引用块（D51）：划选主路径 / 随手问浮窗「添加到主对话」挂在输入框上方 */
  refs?: RefChip[]
  onRemoveRef?: (id: string) => void
  /**
   * 多模态拍题面板（F 板块）的挂载槽位。
   *
   * 做成 render prop 而不是在这里 import MediaCapturePanel，是为了让 F 的依赖单向：
   * 本文件完全不认识 F，F 通过这个槽位把自己的 UI 塞进来。这样 B 侧（输入区）不会
   * 因为 F 的实现变化而被动改动，也不会出现「B 引用 F」这种方向混乱的依赖。
   *
   * {@link https://github.com/vercel/composition-patterns}
   */
  renderMediaCapture?: () => ReactNode
}

export default function InputArea({
  value,
  onChange,
  onSend,
  disabled,
  inputRef,
  renderQuickPanel,
  refs = [],
  onRemoveRef,
  renderMediaCapture,
}: InputAreaProps) {
  const [quickOpen, setQuickOpen] = useState(false)

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!disabled && value.trim()) onSend()
    }
  }

  /** 输入框高度自适应 */
  const autoResize = () => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`
  }

  const closeQuick = () => setQuickOpen(false)

  return (
      <div className="chat-input-wrap">
        {/* 引用块（D51 / F 板块复用的通用组件） */}
        <ReferenceChips refs={refs} onRemoveRef={onRemoveRef} />

        {/* 多模态拍题（F 板块）：挂在输入框上方、引用块下方，随消息一起发出。
            放在 chat-input-bar 之前而非之后，是为了不让它把底栏顶出可视区。 */}
        {renderMediaCapture?.()}

        {/* 快捷引用浮层 */}
      {quickOpen && (
        <>
          <div className="chat-quick-mask" onClick={closeQuick} aria-hidden="true" />
          <div className="chat-quick-pop glass">{renderQuickPanel(closeQuick)}</div>
        </>
      )}

      <div className="chat-input-bar glass">
        <button
          type="button"
          className="chat-input-plus"
          onClick={() => setQuickOpen((v) => !v)}
          aria-label="快捷引用"
          aria-expanded={quickOpen}
          title="快捷引用"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>

        <textarea
          ref={inputRef}
          className="chat-input"
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            autoResize()
          }}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，Enter 发送，Shift+Enter 换行…"
          rows={1}
          aria-label="消息输入框"
        />

        <button
          type="button"
          className="chat-input-send"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label="发送"
          title="发送"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M22 2L11 13" />
            <path d="M22 2l-7 20-4-9-9-4 20-7z" />
          </svg>
        </button>
      </div>
    </div>
  )
}

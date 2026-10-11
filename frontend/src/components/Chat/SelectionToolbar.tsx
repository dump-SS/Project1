/**
 * D51 划选工具条：用户选中文本后，在选区附近浮出「引用到主对话 / 随手问」。
 *
 * - 引用到主对话（主路径）：回调 onQuote，调用方把选中文本挂成输入框上的引用块
 * - 随手问（旁路）：回调 onFloat，调用方打开随手问浮窗并预填选中文本
 */
import type { CSSProperties } from 'react'

interface SelectionToolbarProps {
  x: number
  y: number
  text: string
  onQuote: (text: string) => void
  onFloat: (text: string) => void
  onDone?: () => void
}

export default function SelectionToolbar({
  x,
  y,
  text,
  onQuote,
  onFloat,
  onDone,
}: SelectionToolbarProps) {
  const style: CSSProperties = { left: x, top: y }
  const done = onDone ?? (() => {})
  return (
    <div
      className="chat-sel-toolbar"
      style={style}
      // 屏蔽全局划选监听：在工具条内的 mousedown/mouseup 不应触发「清掉选区/收起工具条」，
      // 否则 click 还没来得及触发，工具条就被卸载、按钮点了没反应。
      onMouseDown={(e) => {
        e.preventDefault()
        e.stopPropagation()
      }}
      onMouseUp={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="chat-sel-btn"
        onClick={() => {
          onQuote(text)
          done()
        }}
        title="引用到主对话"
      >
        在主对话追问
      </button>
      <button
        type="button"
        className="chat-sel-btn"
        onClick={() => {
          onFloat(text)
          done()
        }}
        title="随手问"
      >
        随手问
      </button>
    </div>
  )
}
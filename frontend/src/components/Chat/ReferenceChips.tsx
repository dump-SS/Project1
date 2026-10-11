/**
 * 引用块·通用组件（D51 / F 板块复用）。
 *
 * 把消息里「引用一段内容置入输入框上方」的 UI 提成可复用组件：
 * - InputArea（Chat 主对话）用它渲染划选主路径 / 随手问「添加到主对话」的引用
 * - F 板块（收藏 / 讲解）引用同一份协议（RefChip），打标自己的来源（source）
 */
import type { RefChip } from './types'

interface ReferenceChipsProps {
  refs: RefChip[]
  /** 点击 ✕ 移除引用 */
  onRemoveRef?: (id: string) => void
}

export default function ReferenceChips({ refs, onRemoveRef }: ReferenceChipsProps) {
  if (!refs || refs.length === 0) return null
  return (
    <div className="chat-ref-chips">
      {refs.map((r) => (
        <span key={r.id} className="chat-ref-chip" data-source={r.source ?? ''}>
          <span className="chat-ref-chip-label">{r.label}</span>
          <span className="chat-ref-chip-text">{r.text}</span>
          <button
            type="button"
            className="chat-ref-chip-x"
            onClick={() => onRemoveRef?.(r.id)}
            aria-label="移除引用"
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  )
}
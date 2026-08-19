/**
 * 左侧面板 · 快速引用（三个 Tab）：
 * - Tab A「我的错题」：localStorage 读取（与错题本页共享 key），点击填入输入框
 * - Tab B「知识点速查」：KNOWLEDGE_BASE 硬编码列表，点击填入输入框
 * - Tab C「快捷提问」：硬编码常用问题，点击直接发送
 *
 * compact=true 时作为输入区「+」浮层的精简版渲染。
 */

import { useEffect, useState } from 'react'
import { KNOWLEDGE_BASE, masteryTone } from '@/utils/matchKnowledge'
import { QUICK_QUESTIONS } from '@/pages/Chat/mockData'
import {
  readAllErrors,
  relativeTime,
  REASON_LABEL,
  SUBJECT_LABEL,
  type ErrorItem,
  type Subject,
} from './types'

type TabKey = 'errors' | 'knowledge' | 'quick'

interface ReferencePanelProps {
  /** 填入输入框并聚焦（错题 / 知识点） */
  onFillInput: (text: string) => void
  /** 直接作为用户消息发送（快捷提问） */
  onSendQuick: (text: string) => void
  /** 精简版（浮层用）：更紧凑的行距与字号 */
  compact?: boolean
  /** 录入错题后 +1，触发错题列表重读 */
  refreshKey?: number
  /** 点击任意条目后的回调（浮层用来关闭自己） */
  onPicked?: () => void
}

const TABS: { key: TabKey; label: string }[] = [
  { key: 'errors', label: '我的错题' },
  { key: 'knowledge', label: '知识点速查' },
  { key: 'quick', label: '快捷提问' },
]

export default function ReferencePanel({
  onFillInput,
  onSendQuick,
  compact,
  refreshKey,
  onPicked,
}: ReferencePanelProps) {
  const [tab, setTab] = useState<TabKey>('errors')
  const [errors, setErrors] = useState<(ErrorItem & { subject: Subject })[]>([])

  // 初次挂载 + 录入新错题后重读 localStorage
  useEffect(() => {
    setErrors(readAllErrors())
  }, [refreshKey])

  const pickFill = (text: string) => {
    onFillInput(text)
    onPicked?.()
  }

  const pickSend = (text: string) => {
    onSendQuick(text)
    onPicked?.()
  }

  return (
    <div className={`ref-panel ${compact ? 'ref-panel-compact' : ''}`}>
      {/* Tab 头 */}
      <div className="ref-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`ref-tab ${tab === t.key ? 'ref-tab-active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab A：我的错题 */}
      {tab === 'errors' && (
        <div className="ref-list" role="tabpanel">
          {errors.length === 0 && (
            <p className="ref-empty">还没有错题记录，去右侧录入一条吧 📝</p>
          )}
          {errors.map((e) => (
            <button
              key={e.id}
              type="button"
              className="ref-item"
              onClick={() => pickFill(`帮我解析这道错题：${e.questionText}`)}
              title="点击填入输入框"
            >
              <span className="ref-item-text">{e.questionText}</span>
              <span className="ref-item-tags">
                <span className="ref-tag ref-tag-subject">{SUBJECT_LABEL[e.subject]}</span>
                {e.knowledgeNames.map((k) => (
                  <span key={k} className="ref-tag ref-tag-kp">
                    {k}
                  </span>
                ))}
                <span className="ref-tag ref-tag-reason">{REASON_LABEL[e.reason]}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Tab B：知识点速查 */}
      {tab === 'knowledge' && (
        <div className="ref-list" role="tabpanel">
          {KNOWLEDGE_BASE.map((k) => (
            <button
              key={k.name}
              type="button"
              className="ref-item"
              onClick={() =>
                pickFill(`请解释一下「${k.name}」，我的掌握度是 ${Math.round(k.mastery * 100)}%`)
              }
              title="点击填入输入框"
            >
              <span className="ref-item-head">
                <span className={`ref-mastery-dot ref-mastery-${masteryTone(k.mastery)}`} />
                <span className="ref-item-name">{k.name}</span>
                <span className="ref-item-pct">{Math.round(k.mastery * 100)}%</span>
              </span>
              <span className="ref-item-def">{k.definition}</span>
            </button>
          ))}
        </div>
      )}

      {/* Tab C：快捷提问 */}
      {tab === 'quick' && (
        <div className="ref-list" role="tabpanel">
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              className="ref-item ref-item-quick"
              onClick={() => pickSend(q)}
              title="点击直接发送"
            >
              <span className="ref-item-text">{q}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M22 2L11 13" />
                <path d="M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </button>
          ))}
        </div>
      )}

      {!compact && errors.length > 0 && tab === 'errors' && (
        <p className="ref-footnote">最近一条录入于 {relativeTime(errors[0].createdAt)}</p>
      )}
    </div>
  )
}

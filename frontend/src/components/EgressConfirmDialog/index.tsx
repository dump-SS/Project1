/**
 * 带图出域确认弹窗（A1，2026-11-27 Skyer 复核）。
 *
 * 文案口径：不出现「出域 / 开关 / data_class」等内部术语（visual-language §6.2），
 * 但必须说清「照片会发给 AI」，不能只用「不再显示」把权限变更包装成隐藏提示。
 * 勾选框**默认不勾**；勾选 + 继续才会把 `knowledgeAiEgressEnabled` 置 true。
 */
import { useEffect, useState } from 'react'

import Toast from '@/components/Toast'
import { updateSettings } from '@/services/settings'
import { EGRESS_CONFIRM_EVENT, resolveEgressConfirm } from '@/services/egressConfirm'
import styles from './index.module.css'

export default function EgressConfirmDialog() {
  const [open, setOpen] = useState(false)
  const [remember, setRemember] = useState(false)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    const onAsk = () => {
      setRemember(false)
      setOpen(true)
    }
    window.addEventListener(EGRESS_CONFIRM_EVENT, onAsk)
    return () => window.removeEventListener(EGRESS_CONFIRM_EVENT, onAsk)
  }, [])

  const finish = (ok: boolean) => {
    setOpen(false)
    resolveEgressConfirm(ok)
  }

  const onContinue = async () => {
    if (remember) {
      setSaving(true)
      try {
        await updateSettings({ knowledgeAiEgressEnabled: true })
      } catch {
        // 保存失败**不阻断本次**：单次授权已经成立，照片仍可识别。
        // 但必须让用户知道「下次还会问」，不能静默——这正是 A1 的要求。
        setToast('设置没保存，下次还会问你')
      } finally {
        setSaving(false)
      }
    }
    finish(true)
  }

  if (!open) {
    return toast ? <Toast text={toast} onDone={() => setToast('')} /> : null
  }

  return (
    <>
      <div className={styles.mask} role="presentation" onClick={() => finish(false)} />
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="egress-confirm-title"
        aria-describedby="egress-confirm-body"
      >
        <h2 id="egress-confirm-title" className={styles.title}>
          这张照片要发给 AI 识别
        </h2>
        <p id="egress-confirm-body" className={styles.body}>
          这张照片会发给 AI 识别题目内容。识别完只留下题面和你拍的原图，不会用到别的地方。
        </p>
        <label className={styles.remember}>
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            disabled={saving}
          />
          <span>以后直接识别，不用再问我（可以在设置里改回来）</span>
        </label>
        <div className={styles.actions}>
          <button type="button" className={styles.cancel} onClick={() => finish(false)} disabled={saving}>
            取消
          </button>
          <button type="button" className={styles.primary} onClick={onContinue} disabled={saving}>
            {saving ? '保存中…' : '继续'}
          </button>
        </div>
      </div>
      {toast && <Toast text={toast} onDone={() => setToast('')} />}
    </>
  )
}

/**
 * 多模态拍题面板（F 板块最小闭环的 UI 一半）。
 *
 * 职责：选图 → 上传到私有 R2（经后端代理）→ 预览 → 把产物交出去。
 * **不做识别**：这一轮只打通「图片存得下、取得到」，OCR/题目解析留给后续派活
 * （原 OCR 占位实现已被移除，这里不再假装能识别）。
 *
 * ## 为什么不改 ChatCards.tsx
 *
 * B 的 ChatCards 由 dev-1 并行改造（埋点）。F 的引用块与契约 ChatCard 同构，
 * 且 ChatCards 对未知 type 有 title-only 兜底，所以本组件只负责
 * 「上传」与「按 key 取回并渲染」，不进 B 的渲染路径，两边零冲突。
 *
 * ## 取回为什么要走 fetchMedia 而不是直接 <img src={getUrl}>
 *
 * 直接拼 URL 会让浏览器裸奔，绕过 `credentials: 'include'`，cookie 鉴权就挂了
 * （后端要 `Depends(current_user)`）。所以取回统一经 services，再 createObjectURL。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import {
  ACCEPTED_IMAGE_TYPES,
  MAX_UPLOAD_BYTES,
  fetchMedia,
  uploadMedia,
  type FCard,
  type MediaUploadResult,
  toFileSummaryCard,
  validateImageFile,
} from '../../services/fMedia'
import styles from './index.module.css'

export interface MediaCapturePanelProps {
  /** 上传成功回调：把 file_summary 引用块交给外层（通常塞进对话上下文栈）。 */
  onCard?: (card: FCard, result: MediaUploadResult) => void
  /** 紧凑形态：内嵌在输入区时省掉大标题 */
  compact?: boolean
}

type Phase = 'idle' | 'uploading' | 'loading' | 'ready' | 'error'

export default function MediaCapturePanel({ onCard, compact = false }: MediaCapturePanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const objectUrlRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [result, setResult] = useState<MediaUploadResult | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [tip, setTip] = useState<string | null>(null)

  /** 组件卸载时务必 revoke，否则 blob URL 会一直占着内存 */
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    }
  }, [])

  const releasePreview = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setPreview(null)
  }, [])

  /** 取回预览：后端代理读 R2，而不是复用本地 file:// */
  const loadPreview = useCallback(async (key: string) => {
    setPhase('loading')
    try {
      const blob = await fetchMedia(key)
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
      const url = URL.createObjectURL(blob)
      objectUrlRef.current = url
      setPreview(url)
      setPhase('ready')
    } catch (err) {
      setPhase('error')
      setTip(err instanceof Error ? `图片取回失败：${err.message}` : '图片取回失败')
    }
  }, [])

  const handleFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      // 允许重选同一个文件
      event.target.value = ''
      if (!file) return

      const invalid = validateImageFile(file)
      if (invalid) {
        setPhase('error')
        setTip(invalid)
        return
      }

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setPhase('uploading')
      setTip(null)
      try {
        const uploaded = await uploadMedia(file, controller.signal)
        setResult(uploaded)
        // 上传成功即按 §3.1 产出引用块，交给外层消费
        onCard?.(toFileSummaryCard(uploaded, file.name), uploaded)
        await loadPreview(uploaded.key)
      } catch (err) {
        if (controller.signal.aborted) return
        setPhase('error')
        setTip(err instanceof Error ? `上传失败：${err.message}` : '上传失败')
      }
    },
    [loadPreview, onCard],
  )

  const busy = phase === 'uploading' || phase === 'loading'

  return (
    <section className={styles.panel} aria-label="多模态拍题">
      {!compact && (
        <header className={styles.head}>
          <h3 className={styles.title}>拍题上传</h3>
          <p className={styles.subtitle}>
            上传题目图片用于提问。支持 {ACCEPTED_IMAGE_TYPES.join(' / ')}，
            单张不超过 {Math.round(MAX_UPLOAD_BYTES / (1024 * 1024))}MB。
          </p>
        </header>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(',')}
        onChange={handleFile}
        hidden
        data-testid="media-capture-input"
      />

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.pick}
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {phase === 'uploading' ? '上传中…' : phase === 'loading' ? '取回中…' : '选择图片'}
        </button>
        {result && (
          <button
            type="button"
            className={styles.clear}
            onClick={() => {
              releasePreview()
              setResult(null)
              setPhase('idle')
              setTip(null)
            }}
          >
            清除
          </button>
        )}
      </div>

      {tip && (
        <p className={styles.error} role="alert">
          {tip}
        </p>
      )}

      {preview && (
        <figure className={styles.previewWrap}>
          {/* 预览图来自 R2 经后端取回的字节，不是本地 file:// */}
          <img className={styles.preview} src={preview} alt="已上传的题目图片预览" />
          {result && <figcaption className={styles.caption}>已存入私有空间：{result.key}</figcaption>}
        </figure>
      )}
    </section>
  )
}
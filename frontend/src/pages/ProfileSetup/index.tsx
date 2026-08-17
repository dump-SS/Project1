import { useEffect, useState } from 'react'
import styles from './index.module.css'
import { getMe, patchMe, putMe } from '../../services/user'
import { subjectLabels } from '../../styles/theme'
import type { Stage, Subject, User } from '../../types/api'

const STAGES: { value: Stage; label: string }[] = [
  { value: 'junior', label: '初中' },
  { value: 'senior', label: '高中' },
]

const SUBJECTS: Subject[] = [
  'chinese', 'math', 'english', 'physics', 'chemistry',
  'biology', 'history', 'geography', 'politics', 'other',
]

export default function ProfileSetupPage() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [stage, setStage] = useState<Stage | null>(null)
  const [grade, setGrade] = useState('')
  const [subjects, setSubjects] = useState<Subject[]>([])

  const [tip, setTip] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((data) => {
        if (cancelled) return
        setUser(data)
        setStage(data.stage ?? null)
        setGrade(data.grade ?? '')
        setSubjects(data.subjects ?? [])
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : '加载用户资料失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const toggleSubject = (s: Subject) => {
    setSubjects((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))
  }

  const validate = (): string | null => {
    if (!stage) return '请选择学段'
    if (!grade.trim()) return '请填写年级'
    if (subjects.length < 1) return '请至少选择一个学科'
    return null
  }

  const isOnboarding = user ? !user.onboardingCompleted : true

  const handleSubmit = async () => {
    const err = validate()
    if (err) {
      setTip({ type: 'error', msg: err })
      return
    }
    setTip(null)
    setSaving(true)
    try {
      const body = { stage: stage as Stage, grade: grade.trim(), subjects }
      // 未建档 → PUT 全量；已建档 → PATCH 局部更新
      const updated = isOnboarding ? await putMe(body) : await patchMe(body)
      setUser(updated)
      setStage(updated.stage)
      setGrade(updated.grade ?? '')
      setSubjects(updated.subjects ?? [])
      setTip({ type: 'success', msg: isOnboarding ? '建档成功！' : '资料已更新。' })
    } catch (e) {
      setTip({ type: 'error', msg: e instanceof Error ? e.message : '保存失败，请稍后再试' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className={styles.page}><p className={styles.loading}>加载中…</p></div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>资料建档</h1>
        <p className={styles.subtitle}>
          {isOnboarding
            ? '完成以下信息，帮助我们为你规划学习与生成建议。'
            : '你的资料已建档，可随时修改。'}
        </p>
      </header>

      {loadError && <p className={styles.error}>{loadError}</p>}

      <section className={styles.card}>
        <div className={styles.row}>
          <span className={styles.label}>学段</span>
          <div className={styles.optionGroup}>
            {STAGES.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`${styles.optionBtn} ${stage === opt.value ? styles.optionActive : ''}`}
                onClick={() => setStage(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.row}>
          <label className={styles.field}>
            <span className={styles.label}>年级</span>
            <input
              className={styles.textInput}
              value={grade}
              placeholder="如：初二 / 高二"
              maxLength={20}
              onChange={(e) => setGrade(e.target.value)}
            />
          </label>
        </div>

        <div className={styles.row}>
          <span className={styles.label}>学科（可多选）</span>
          <div className={styles.chipGroup}>
            {SUBJECTS.map((s) => (
              <button
                key={s}
                type="button"
                className={`${styles.chip} ${subjects.includes(s) ? styles.chipActive : ''}`}
                onClick={() => toggleSubject(s)}
              >
                {subjectLabels[s] ?? s}
              </button>
            ))}
          </div>
        </div>

        {tip && <p className={tip.type === 'success' ? styles.success : styles.error}>{tip.msg}</p>}

        <button type="button" className={styles.submitBtn} disabled={saving} onClick={handleSubmit}>
          {saving ? '保存中…' : isOnboarding ? '完成建档' : '保存修改'}
        </button>
      </section>
    </div>
  )
}

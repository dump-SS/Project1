import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import styles from './index.module.css'
import { getMe, patchMe, putMe } from '../../services/user'
import { subjectLabels } from '../../styles/theme'
import GuardianAuthorizationPanel from '../../components/GuardianAuthorizationPanel'
import type { GuardianAuthorizationStatus, Stage, Subject, User } from '../../types/api'

/**
 * 激活式建档流程（D40）——「类似系统激活页」的分步引导 + 完成衔接动画。
 *
 * 步骤：① 基础资料（学段/年级/出生年份）→ ② 学科 → ③（未满 14 岁时强制）监护人授权 → 完成
 *
 * 低龄门槛（D41）由**后端**判定：`PUT /me` 若推算未满 14 周岁且监护人授权未生效，
 * 会照常保存资料但把 `onboardingCompleted` 保持为 false —— 前端以这个字段为准决定
 * 是否进入授权步骤（前端不自己算年龄，避免两边口径漂移）。
 *
 * 授权完成后重调一次 `PUT /me`（幂等）即可置为已完成，然后衔接动画进首页（§1.2）。
 */

const CURRENT_YEAR = new Date().getFullYear()

// 出生年份候选：目标用户是中学生（约 10-22 岁），范围给宽一点但不放未来年份
const BIRTH_YEARS: number[] = Array.from({ length: 13 }, (_, i) => CURRENT_YEAR - 10 - i)

const STAGES: { value: Stage; label: string; grades: { value: string; label: string }[] }[] = [
  {
    value: 'junior',
    label: '初中',
    grades: [
      { value: 'grade_7', label: '初一' },
      { value: 'grade_8', label: '初二' },
      { value: 'grade_9', label: '初三' },
      { value: 'grade_junior_other', label: '其它' },
    ],
  },
  {
    value: 'senior',
    label: '高中',
    grades: [
      { value: 'grade_10', label: '高一' },
      { value: 'grade_11', label: '高二' },
      { value: 'grade_12', label: '高三' },
      { value: 'grade_senior_other', label: '其它' },
    ],
  },
]

const SUBJECTS: Subject[] = ['YW', 'SX', 'YY', 'WL', 'HX', 'SW', 'LS', 'DL', 'ZZ', 'other']

type Step = 'basics' | 'subjects' | 'guardian' | 'done'

const STEP_ORDER: { key: Step; label: string }[] = [
  { key: 'basics', label: '基础资料' },
  { key: 'subjects', label: '学习科目' },
  { key: 'guardian', label: '监护人授权' },
]

export default function ProfileSetupPage() {
  const navigate = useNavigate()

  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [step, setStep] = useState<Step>('basics')
  const [stage, setStage] = useState<Stage | null>(null)
  const [grade, setGrade] = useState('')
  const [birthYear, setBirthYear] = useState<number | null>(null)
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [guardianStatus, setGuardianStatus] = useState<GuardianAuthorizationStatus>('pending')

  const [tip, setTip] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const isOnboarding = user ? !user.onboardingCompleted : true

  const applyUser = useCallback((data: User) => {
    setUser(data)
    setStage(data.stage ?? null)
    setGrade(data.grade ?? '')
    setBirthYear(data.birthYear ?? null)
    setSubjects(data.subjects ?? [])
    setGuardianStatus(data.guardianAuthorization?.status ?? 'pending')
  }, [])

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((data) => {
        if (cancelled) return
        applyUser(data)
        if (data.onboardingCompleted) {
          // 已完成建档 → 直接进入完成态（本页也允许老用户进来改资料）
          setStep('done')
        } else if (data.birthYear) {
          // 之前提交过资料但被低龄门槛拦住 → 从授权步骤继续
          setStep('guardian')
        }
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
  }, [applyUser])

  const toggleSubject = (s: Subject) => {
    setSubjects((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))
  }

  /** 提交建档（幂等 PUT）→ 后端判定低龄门槛，返回真实 onboardingCompleted */
  const submitProfile = useCallback(async (): Promise<User> => {
    const body = {
      stage: stage as Stage,
      grade: grade.trim(),
      subjects,
      birthYear,
    }
    return isOnboarding ? putMe(body) : patchMe(body)
  }, [stage, grade, subjects, birthYear, isOnboarding])

  const handleBasicsNext = () => {
    if (!stage) {
      setTip({ type: 'error', msg: '请选择学段' })
      return
    }
    if (!grade.trim()) {
      setTip({ type: 'error', msg: '请选择年级' })
      return
    }
    if (!birthYear) {
      setTip({ type: 'error', msg: '请选择出生年份（用于判断是否需要监护人授权）' })
      return
    }
    setTip(null)
    setStep('subjects')
  }

  const handleSubjectsSubmit = async () => {
    if (subjects.length < 1) {
      setTip({ type: 'error', msg: '请至少选择一个学科' })
      return
    }
    setTip(null)
    setSaving(true)
    try {
      const updated = await submitProfile()
      applyUser(updated)
      if (updated.onboardingCompleted) {
        setStep('done')
      } else {
        // 后端判定为未满 14 岁且授权未生效（D41 强制门槛）
        setStep('guardian')
        setTip({
          type: 'error',
          msg: '资料已保存。未满 14 周岁需要监护人确认授权后才能完成激活。',
        })
      }
    } catch (e) {
      setTip({ type: 'error', msg: e instanceof Error ? e.message : '保存失败，请稍后再试' })
    } finally {
      setSaving(false)
    }
  }

  /** 授权完成后：重调 PUT /me（幂等）把档案置为已完成 */
  const handleGuardianContinue = async () => {
    setTip(null)
    setSaving(true)
    try {
      const updated = await submitProfile()
      applyUser(updated)
      if (updated.onboardingCompleted) {
        setStep('done')
      } else {
        setTip({
          type: 'error',
          msg: '监护人尚未确认授权。请监护人打开确认链接点确认，然后回到这里点「刷新状态」再继续。',
        })
      }
    } catch (e) {
      setTip({ type: 'error', msg: e instanceof Error ? e.message : '保存失败，请稍后再试' })
    } finally {
      setSaving(false)
    }
  }

  // 完成衔接动画：短暂停留后进首页
  useEffect(() => {
    if (step !== 'done') return
    const timer = window.setTimeout(() => navigate('/study-guide', { replace: true }), 1800)
    return () => window.clearTimeout(timer)
  }, [step, navigate])

  const stepIndex = useMemo(() => {
    if (step === 'done') return STEP_ORDER.length
    const idx = STEP_ORDER.findIndex((s) => s.key === step)
    return idx < 0 ? 0 : idx
  }, [step])

  if (loading) {
    return <div className={styles.page}><p className={styles.loading}>加载中…</p></div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>激活你的学习空间</h1>
        <p className={styles.subtitle}>
          {isOnboarding
            ? '三步完成建档与个性化，之后随时可以在设置里修改。'
            : '你的资料已建档，可随时修改。'}
        </p>
      </header>

      {/* 步骤条（激活感：① ② ③） */}
      <ol className={styles.stepBar} aria-label="激活步骤">
        {STEP_ORDER.map((s, i) => (
          <li
            key={s.key}
            className={`${styles.stepItem} ${i <= stepIndex ? styles.stepItemActive : ''}`}
            aria-current={i === stepIndex ? 'step' : undefined}
          >
            <span className={styles.stepDot}>{i + 1}</span>
            <span className={styles.stepText}>{s.label}</span>
          </li>
        ))}
      </ol>

      {loadError && <p className={styles.error}>{loadError}</p>}

      {step === 'basics' && (
        <section className={styles.card}>
          <div className={styles.row}>
            <span className={styles.label}>学段</span>
            <div className={styles.optionGroup}>
              {STAGES.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`${styles.optionBtn} ${stage === opt.value ? styles.optionActive : ''}`}
                  onClick={() => {
                    // 切换学段时清空年级，避免学段与年级错配（如初中选了"高三"）
                    if (stage !== opt.value) setGrade('')
                    setStage(opt.value)
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.row}>
            <span className={styles.label}>年级</span>
            {stage ? (
              <div className={styles.optionGroup}>
                {(STAGES.find((s) => s.value === stage)?.grades ?? []).map((g) => (
                  <button
                    key={g.value}
                    type="button"
                    className={`${styles.optionBtn} ${grade === g.value ? styles.optionActive : ''}`}
                    onClick={() => setGrade(g.value)}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
            ) : (
              <p className={styles.placeholder}>请先选择学段</p>
            )}
          </div>

          <div className={styles.row}>
            <span className={styles.label}>出生年份</span>
            <select
              className={styles.textInput}
              value={birthYear ?? ''}
              onChange={(e) => setBirthYear(e.target.value ? Number(e.target.value) : null)}
              aria-label="出生年份"
            >
              <option value="">请选择出生年份</option>
              {BIRTH_YEARS.map((y) => (
                <option key={y} value={y}>{y} 年</option>
              ))}
            </select>
            <p className={styles.placeholder}>
              只用于判断是否需要监护人确认授权（未满 14 周岁），不采集精确生日。
            </p>
          </div>

          {tip?.type === 'error' && <p className={styles.error}>{tip.msg}</p>}

          <button type="button" className={styles.submitBtn} onClick={handleBasicsNext}>
            下一步
          </button>
        </section>
      )}

      {step === 'subjects' && (
        <section className={styles.card}>
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

          <div className={styles.actions}>
            <button type="button" className={styles.ghostBtn} onClick={() => setStep('basics')}>
              上一步
            </button>
            <button
              type="button"
              className={styles.submitBtn}
              disabled={saving}
              onClick={handleSubjectsSubmit}
            >
              {saving ? '保存中…' : '完成建档'}
            </button>
          </div>
        </section>
      )}

      {step === 'guardian' && (
        <section className={styles.card}>
          <p className={styles.notice}>
            你填写的年龄未满 14 周岁：按未成年人保护要求，需要监护人确认授权后才能完成激活。
            资料已经保存好了，只差这一步。
          </p>

          <GuardianAuthorizationPanel onStatusChange={setGuardianStatus} compact />

          {tip && <p className={tip.type === 'success' ? styles.success : styles.error}>{tip.msg}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.ghostBtn} onClick={() => setStep('subjects')}>
              返回上一步
            </button>
            <button
              type="button"
              className={styles.submitBtn}
              disabled={saving || guardianStatus !== 'active'}
              onClick={handleGuardianContinue}
              title={guardianStatus !== 'active' ? '监护人确认后即可继续' : undefined}
            >
              {saving
                ? '检查中…'
                : guardianStatus === 'active'
                  ? '授权已生效，完成激活'
                  : '等待监护人确认…'}
            </button>
          </div>
        </section>
      )}

      {step === 'done' && (
        <section className={`${styles.card} ${styles.doneCard}`} role="status">
          <div className={styles.doneBadge} aria-hidden="true">✓</div>
          <h2 className={styles.doneTitle}>激活完成</h2>
          <p className={styles.doneText}>
            正在进入你的学习空间… 若没有自动跳转，
            <button
              type="button"
              className={styles.inlineLink}
              onClick={() => navigate('/study-guide', { replace: true })}
            >
              点这里
            </button>
            。
          </p>
        </section>
      )}
    </div>
  )
}

/**
 * 模块三 · 页面 1：匿名数值上传页（/community/upload）
 * ------------------------------------------------------------
 * 纯前端 mock：不收集任何身份信息，数据只写 localStorage。
 * 提交成功后按钮变「已提交 ✓」并自动跳转对比页；
 * 刷新页面后可重新提交（不持久化"已提交"状态，不阻塞）。
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import styles from './index.module.css'
import { subjectLabels } from '../../styles/theme'
import {
  COMMUNITY_SUBJECTS,
  ensurePool,
  saveMyData,
  type CommunityRecord,
  type CommunitySubject,
} from './community'

interface SliderFieldProps {
  label: string
  value: number
  min: number
  max: number
  unit: string
  hint?: string
  onChange: (v: number) => void
}

/** 单项一行：左侧标签，右侧滑杆 + 当前值 */
function SliderField({ label, value, min, max, unit, hint, onChange }: SliderFieldProps) {
  // 滑杆已填充比例，用于轨道渐变色（CSS 变量 --fill）
  const fill = ((value - min) / (max - min)) * 100
  return (
    <div className={styles.fieldRow}>
      <div className={styles.fieldLabel}>
        <span>{label}</span>
        {hint && <em>{hint}</em>}
      </div>
      <div className={styles.fieldControl}>
        <input
          type="range"
          className={styles.slider}
          min={min}
          max={max}
          step={1}
          value={value}
          aria-label={label}
          style={{ '--fill': `${fill}%` } as React.CSSProperties}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className={`${styles.fieldValue} numeric`}>
          {value}
          <small>{unit}</small>
        </span>
      </div>
    </div>
  )
}

export default function CommunityUploadPage() {
  const navigate = useNavigate()

  const [hours, setHours] = useState(14)
  const [focus, setFocus] = useState(3)
  const [fatigue, setFatigue] = useState(3)
  const [completion, setCompletion] = useState(70)
  const [subject, setSubject] = useState<CommunitySubject>('SX')
  const [submitted, setSubmitted] = useState(false)

  // 首次进入时确保群体池存在（20 条预置假数据）
  useEffect(() => {
    ensurePool()
  }, [])

  const handleSubmit = () => {
    if (submitted) return
    const record: CommunityRecord = { hours, focus, fatigue, completion, subject }
    saveMyData(record)
    setSubmitted(true)
    // 稍作停留让用户看到「已提交 ✓」反馈，再自动跳转对比页
    window.setTimeout(() => navigate('/community/compare'), 800)
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>匿名群体对比</h1>
          <p className={styles.pageSubtitle}>
            不记名、不关联账号。提交你的本周学习状态，看看自己在同龄群体中的位置。
          </p>
        </header>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>我的本周状态</h2>

          <SliderField
            label="本周学习时长"
            hint="0-40 小时"
            value={hours}
            min={0}
            max={40}
            unit="小时"
            onChange={setHours}
          />
          <SliderField
            label="平均每日专注度"
            hint="1 无法集中 · 5 高度专注"
            value={focus}
            min={1}
            max={5}
            unit="分"
            onChange={setFocus}
          />
          <SliderField
            label="平均每日疲劳度"
            hint="1 很轻松 · 5 很疲惫"
            value={fatigue}
            min={1}
            max={5}
            unit="分"
            onChange={setFatigue}
          />
          <SliderField
            label="本周完成率"
            hint="计划任务的完成比例"
            value={completion}
            min={0}
            max={100}
            unit="%"
            onChange={setCompletion}
          />

          <div className={styles.fieldRow}>
            <div className={styles.fieldLabel}>
              <span>学科</span>
              <em>用于同学科精准对比</em>
            </div>
            <div className={styles.fieldControl}>
              <select
                className={styles.select}
                value={subject}
                aria-label="学科"
                onChange={(e) => setSubject(e.target.value as CommunitySubject)}
              >
                {COMMUNITY_SUBJECTS.map((s) => (
                  <option key={s} value={s}>
                    {subjectLabels[s]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <p className={styles.privacyNote}>
            本页为纯前端演示：数据仅保存在你自己的浏览器中，不会上传到服务器，也无法关联到你的身份。
          </p>

          <button
            type="button"
            className={`${styles.submitBtn} ${submitted ? styles.submitBtnDone : ''}`}
            disabled={submitted}
            onClick={handleSubmit}
          >
            {submitted ? '已提交 ✓' : '匿名提交'}
          </button>
        </section>

        <p className={styles.pageFooter}>everyone studies at their own pace.</p>
      </div>
    </div>
  )
}

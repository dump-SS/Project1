import { useEffect, useState } from 'react'
import { ConfigProvider, Switch } from 'antd'
import { getSettings, updateSettings } from '@/services/settings'
import { isNetworkError } from '@/services/http'
import { antdThemeToken } from '@/styles/theme'
import styles from './index.module.css'

const SWITCH_ITEMS = [
  {
    key: 'aiWeightTuningEnabled',
    title: 'AI 自动调权',
    description:
      '开启后，系统会在受限区间内参考 AI 建议动态调整状态权重；关闭后固定使用默认权重（PRD 5.2）。具体权重数值不会对用户展示。',
  },
  {
    key: 'sendTextToAI',
    title: '发送文字内容给第三方 AI',
    description:
      '开启后，你填写的学习目标描述、任务备注等文字会发送给第三方 AI 服务，用于生成更贴合的建议。关闭后你填写的文字不会发送给第三方 AI，仅使用结构化特征生成建议（PRD 6.2 明示告知）。',
  },
]

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [error, setError] = useState('')
  const [values, setValues] = useState({
    aiWeightTuningEnabled: true,
    sendTextToAI: false,
  })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getSettings()
      .then((data) => {
        if (cancelled) return
        setValues({
          aiWeightTuningEnabled: data.aiWeightTuningEnabled,
          sendTextToAI: data.sendTextToAI,
        })
      })
      .catch((err) => {
        if (cancelled) return
        setError(
          isNetworkError(err)
            ? '设置服务暂不可用，请稍后再试'
            : err?.message ?? '读取设置失败',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleToggle = async (key, checked) => {
    setSavingKey(key)
    setError('')
    try {
      const data = await updateSettings({ [key]: checked })
      setValues({
        aiWeightTuningEnabled: data.aiWeightTuningEnabled,
        sendTextToAI: data.sendTextToAI,
      })
    } catch (err) {
      setError(
        isNetworkError(err)
          ? '设置服务暂不可用，请稍后再试'
          : err?.message ?? '保存设置失败',
      )
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <ConfigProvider theme={{ token: antdThemeToken }}>
      <main className={styles.page}>
        <div className={styles.container}>
          <h1 className={styles.title}>设置</h1>
          <p className={styles.subtitle}>你的数据边界由你决定</p>

          <section className={styles.card}>
            {SWITCH_ITEMS.map((item) => (
              <div className={styles.item} key={item.key}>
                <div className={styles.itemBody}>
                  <h2 className={styles.itemTitle}>{item.title}</h2>
                  <p className={styles.itemDesc}>{item.description}</p>
                </div>
                <div className={styles.switchWrap}>
                  <Switch
                    checked={values[item.key]}
                    loading={savingKey === item.key}
                    disabled={loading}
                    onChange={(checked) => handleToggle(item.key, checked)}
                  />
                </div>
              </div>
            ))}

            {loading ? <p className={styles.hint}>设置加载中…</p> : null}
            {error ? <p className={styles.error}>{error}</p> : null}
          </section>
        </div>
      </main>
    </ConfigProvider>
  )
}

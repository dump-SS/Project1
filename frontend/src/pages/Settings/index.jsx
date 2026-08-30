import { useEffect, useState } from 'react'
import { ConfigProvider, Switch } from 'antd'
import { getSettings, updateSettings } from '@/services/settings'
import { isNetworkError, apiGet, apiPost } from '@/services/http'
import { fetchCommunityConsent, putCommunityConsent } from '@/services/communityApi'
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
  {
    key: 'knowledgeAiEgressEnabled',
    title: '知识复盘 AI 出域',
    description:
      '开启后，学科知识复盘可调用云端 AI 生成（仅发送经过 EgressGuard 白名单校验的结构化特征，错题原文/作答/答案永不上传）。关闭后知识复盘使用本地规则模板（PRD 12.6）。',
  },
]

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [error, setError] = useState('')
  const [values, setValues] = useState({
    aiWeightTuningEnabled: true,
    sendTextToAI: false,
    knowledgeAiEgressEnabled: false,
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
          knowledgeAiEgressEnabled: data.knowledgeAiEgressEnabled ?? false,
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
        knowledgeAiEgressEnabled: data.knowledgeAiEgressEnabled ?? false,
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

          <CommunityConsentPanel />

          <WeightPanel />
        </div>
      </main>
    </ConfigProvider>
  )
}


// ===== 匿名群体参照授权面板（板块三 M4，决策 v1.7 §4.10） =====

function CommunityConsentPanel() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchCommunityConsent()
      .then((d) => { if (!cancelled) setEnabled(d.enabled); })
      .catch(() => { if (!cancelled) setErr('授权状态读取失败，请稍后再试'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const toggle = async (checked) => {
    setSaving(true);
    setErr('');
    try {
      const d = await putCommunityConsent(checked, checked ? true : undefined);
      setEnabled(d.enabled);
    } catch (e) {
      setErr(isNetworkError(e) ? '服务暂不可用，请稍后再试' : (e?.message ?? '保存失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.card}>
      <div className={styles.item}>
        <div className={styles.itemBody}>
          <h2 className={styles.itemTitle}>匿名群体参照</h2>
          <p className={styles.itemDesc}>
            开启后，你本周的「分桶后的统计特征」（学习时长 / 专注度 / 疲劳度 / 计划完成度）会参与同龄群体的匿名对比；
            不上传任何原始学习内容、错题或自评文本。默认关闭，可随时撤回，撤回后历史特征删除并退出聚合。
            参与需经监护人授权。群体样本不足时不会展示对比，避免误导。
            <br />
            <em>本产品由学生团队开发，上述文案未经专业法律审核。</em>
          </p>
        </div>
        <div className={styles.switchWrap}>
          <Switch
            checked={enabled}
            loading={saving || loading}
            disabled={loading}
            onChange={toggle}
          />
        </div>
      </div>
      {err ? <p className={styles.error}>{err}</p> : null}
    </section>
  );
}

// ===== AI 调权面板（PRD 5.2 / 6.5） =====

function WeightPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tuning, setTuning] = useState(false);
  const [tuneTip, setTuneTip] = useState(null);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    apiGet('/me/weight-config')
      .then(setData)
      .catch((e) => setError(isNetworkError(e) ? '权重服务暂不可用' : (e?.message ?? '读取失败')))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleTune = async () => {
    setTuning(true);
    setTuneTip(null);
    try {
      const r = await apiPost('/me/weight-config/tune-now');
      setTuneTip({ type: r.tuned ? 'ok' : 'err', text: r.message });
      load();
    } catch (e) {
      setTuneTip({ type: 'err', text: e?.message ?? '调权失败' });
    } finally {
      setTuning(false);
    }
  };

  return (
    <section className={styles.weightCard}>
      <div className={styles.weightHeader}>
        <div>
          <h2 className={styles.weightTitle}>AI 调权</h2>
          <p className={styles.weightDesc}>
            系统按周期参考你的学习状态特征微调权重；偏离区间会自动回退（PRD 5.2）。
          </p>
        </div>
        <button
          type="button"
          className={styles.tuneBtn}
          onClick={handleTune}
          disabled={tuning || loading}
        >
          {tuning ? '调权中…' : '立即调权一次'}
        </button>
      </div>

      {error && <p className={styles.weightError}>{error}</p>}
      {tuneTip && (
        <p className={tuneTip.type === 'ok' ? styles.weightOk : styles.weightError}>
          {tuneTip.text}
        </p>
      )}

      {data && (
        <>
          <div className={styles.weightGrid}>
            <WeightCell label="α 行为子分权重" value={data.current.alpha} />
            <WeightCell label="β 自评子分权重" value={data.current.beta} />
            <WeightCell label="w1 完成度" value={data.current.w1} />
            <WeightCell label="w2 正确率" value={data.current.w2} />
            <WeightCell label="w3 节奏稳定度" value={data.current.w3} />
            <WeightCell label="w4 专注度" value={data.current.w4} />
            <WeightCell label="w5 反向疲劳" value={data.current.w5} />
            <WeightCell label="w6 情绪正向" value={data.current.w6} />
          </div>
          <p className={styles.weightUpdatedAt}>
            上次更新：{new Date(data.updatedAt).toLocaleString('zh-CN')}
          </p>

          <h3 className={styles.logTitle}>最近调权日志（{data.recentLogs.length}/5）</h3>
          {data.recentLogs.length === 0 ? (
            <p className={styles.logEmpty}>暂无调权记录</p>
          ) : (
            <ul className={styles.logList}>
              {data.recentLogs.map((log) => (
                <li key={log.id} className={styles.logItem}>
                  <div className={styles.logTop}>
                    <span className={styles.logTime}>
                      {new Date(log.effectiveAt).toLocaleString('zh-CN')}
                    </span>
                    {log.reverted ? (
                      <span className={styles.logTagReverted}>已回退</span>
                    ) : (
                      <span className={styles.logTagOk}>已生效</span>
                    )}
                  </div>
                  <p className={styles.logReason}>{log.reason}</p>
                  {log.reverted && log.revertReason && (
                    <p className={styles.logRevertReason}>回退原因：{log.revertReason}</p>
                  )}
                  <details className={styles.logDetail}>
                    <summary>查看前后权重对比</summary>
                    <div className={styles.logCompare}>
                      <div>
                        <strong>调整前</strong>
                        <pre>{JSON.stringify(log.before, null, 2)}</pre>
                      </div>
                      <div>
                        <strong>调整后</strong>
                        <pre>{JSON.stringify(log.after, null, 2)}</pre>
                      </div>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function WeightCell({ label, value }) {
  return (
    <div className={styles.weightCell}>
      <span className={styles.weightCellLabel}>{label}</span>
      <span className={styles.weightCellValue}>{value.toFixed(3)}</span>
    </div>
  );
}

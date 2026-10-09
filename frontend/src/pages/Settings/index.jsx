import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConfigProvider, Modal, Switch } from 'antd'
import { getSettings, updateSettings } from '@/services/settings'
import { isNetworkError, apiGet, apiPost } from '@/services/http'
import { fetchCommunityConsent, putCommunityConsent } from '@/services/communityApi'
import { getMe } from '@/services/user'
import { useAuth } from '@/context/AuthContext.jsx'
import GuardianAuthorizationPanel from '@/components/GuardianAuthorizationPanel'
import GovernancePanel from './GovernancePanel' // G 板块：用量 / 奖章 / 报错常驻入口
import { antdThemeToken } from '@/styles/theme'
import styles from './index.module.css'

/**
 * 设置（D42 瘦身口径：只留「账号与资料」+「授权与隐私」两个子页）。
 *
 * - 授权与隐私（A 板块 / D41）：AI 三开关 + #29b 提升体验开关 + 匿名群体参照 + 监护人授权；
 * - 账号与资料：邮箱与建档入口，以及既有面板（AI 调权面板按 D42 归 E 板块 M4 下线，暂留）。
 *
 * 子页状态走 `?tab=privacy`（可深链）：建档流程、群体参照被拦时都能直接把用户送到这里。
 */

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
  {
    key: 'userContentEmbeddingApiEnabled',
    // 这一项要弹窗二次确认、且未成年未授权时要置灰，走专用渲染分支（见 UserContentEmbeddingConsent）
    needsConsent: true,
    title: '内容向量化使用第三方服务',
    description:
      '开启后，你在错题里写的原文、你的作答内容、以及学习记录里的文字，会发送给第三方向量化服务转换成检索用的向量，语义检索会更准。默认关闭：关闭时这些内容只在本机用本地模型处理、不发送；本地模型不可用时检索会退回到字面匹配，找得没那么准，但仍然不会发送。你可以随时关掉。',
  },
  {
    key: 'experienceImprovementEnabled',
    title: '将个人数据用于提升体验',
    description:
      '开启后，你的学习数据可能被用于改进 EpochX 的体验（#29b）。默认关闭：未开启时，个人数据不进入任何产品改进用途；你可以随时关闭。',
  },
]

const EMPTY_VALUES = {
  aiWeightTuningEnabled: true,
  sendTextToAI: false,
  knowledgeAiEgressEnabled: false,
  userContentEmbeddingApiEnabled: false,
  experienceImprovementEnabled: false,
}

const UCE_KEY = 'userContentEmbeddingApiEnabled'

/** 把 GET/PATCH /me/settings 的返回收敛成页面状态；字段缺失一律取契约默认值（契约里都是 opt-in → false）。 */
function toSettingsValues(data) {
  return {
    aiWeightTuningEnabled: data.aiWeightTuningEnabled,
    sendTextToAI: data.sendTextToAI,
    knowledgeAiEgressEnabled: data.knowledgeAiEgressEnabled ?? false,
    userContentEmbeddingApiEnabled: data.userContentEmbeddingApiEnabled ?? false,
    experienceImprovementEnabled: data.experienceImprovementEnabled ?? false,
  }
}

/**
 * 后端是否已经落地 userContentEmbeddingApiEnabled 这个 key。
 *
 * 契约里它是 `Settings.required`（openapi.yaml:3823），所以「key 不存在」按契约是后端违约，
 * 不是正常状态。但当下后端确实还没实现（dev-2 并行在做），如果只写 `?? false`，
 * 用户点「开启」会得到 200、返回值里没这个 key、于是「开了又跳回关」——
 * 现象看起来就像功能坏了。
 *
 * 所以这里用 `in`（而不是 `?? false`）把「不存在」和「等于 false」分开：
 * 前者置灰 + 说明「接入中」，后者是正常的「关」。**后端一上线这个判断自动失效，
 * 不需要再改一次前端。** 这是一次性脚手架，判据来自契约而不是版本号，所以不会腐烂。
 */
function hasUCEKey(data) {
  return Object.prototype.hasOwnProperty.call(data ?? {}, UCE_KEY)
}

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') === 'privacy' ? 'privacy' : 'account'

  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [error, setError] = useState('')
  const [values, setValues] = useState(EMPTY_VALUES)
  const [uceAvailable, setUceAvailable] = useState(false)

  /** GET 与 PATCH 的返回走同一条路：既刷值，也刷「后端有没有这个 key」。 */
  const applySettings = (data) => {
    setValues(toSettingsValues(data))
    setUceAvailable(hasUCEKey(data))
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getSettings()
      .then((data) => {
        if (cancelled) return
        applySettings(data)
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
    if (key === UCE_KEY) return
    setSavingKey(key)
    setError('')
    try {
      const data = await updateSettings({ [key]: checked })
      applySettings(data)
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

          {/* 子页切换（D42：账号与资料 / 授权与隐私） */}
          <div className={styles.tabs} role="tablist" aria-label="设置分类">
            <button
              role="tab"
              aria-selected={tab === 'account'}
              className={`${styles.tab} ${tab === 'account' ? styles.tabActive : ''}`}
              onClick={() => setSearchParams({}, { replace: true })}
            >
              账号与资料
            </button>
            <button
              role="tab"
              aria-selected={tab === 'privacy'}
              className={`${styles.tab} ${tab === 'privacy' ? styles.tabActive : ''}`}
              onClick={() => setSearchParams({ tab: 'privacy' }, { replace: true })}
            >
              授权与隐私
            </button>
          </div>

          {tab === 'privacy' && (
            <>
              <section className={styles.card}>
                <p className={styles.sectionHint}>
                  以下开关决定你的数据被怎么用。默认都取最保守的一侧，随时可以改回来。
                </p>

                {SWITCH_ITEMS.map((item) =>
                  item.needsConsent ? (
                    <UserContentEmbeddingConsent
                      key={item.key}
                      item={item}
                      value={values[item.key]}
                      available={uceAvailable}
                      pageDisabled={loading}
                      onSaved={applySettings}
                    />
                  ) : (
                    <div className={styles.item} key={item.key}>
                      <div className={styles.itemBody}>
                        <h2 className={styles.itemTitle}>
                          {item.title}
                          {item.key === 'experienceImprovementEnabled' && (
                            <span className={styles.defaultTag}>默认关闭</span>
                          )}
                        </h2>
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
                  ),
                )}

                {loading ? <p className={styles.hint}>设置加载中…</p> : null}
                {error ? <p className={styles.error}>{error}</p> : null}
              </section>

              <CommunityConsentPanel />

              <GuardianAuthorizationPanel />
            </>
          )}

          {tab === 'account' && (
            <>
              <AccountPanel />
              <WeightPanel />
              <GovernancePanel />
            </>
          )}
        </div>
      </main>
    </ConfigProvider>
  )
}


// ===== 用户内容向量化的第三方服务开关（PRD 12.6 / D34 / D41） =====
// 三条硬要求的出处都在契约里，不是我们自己加的规矩：
// - 开启必须弹窗告知并二次确认 → Settings.userContentEmbeddingApiEnabled 描述
// - 未成年未授权禁止开启，且要区分两个 403 → PATCH /me/settings 的 403 定义
// - 撤回（置 false）不受授权状态限制 → Settings 描述「撤回（置 false）不受授权状态限制」
//   所以「置灰」只作用在「关 → 开」这一侧：一旦开过，永远留可关。

const GUARDIAN_REQUIRED = 'GUARDIAN_AUTHORIZATION_REQUIRED'
const GUARDIAN_EXPIRED = 'GUARDIAN_AUTHORIZATION_EXPIRED'

const GUARDIAN_HINT = {
  required: '开启前需要先完成监护人授权：在本页下方「监护人授权」里确认后即可开启。',
  expired: '监护人授权已过期或已被撤回，需要重新确认后才能开启。',
}

/**
 * 是否「可能未满 14 周岁」——与后端 routes/user.py 的 _is_under_14 同口径：
 * `今年 - birthYear <= 14` 判为需要监护人授权；birthYear 缺失按「不拦」处理。
 *
 * 这里只用来决定「要不要提前把开关置灰」；真正的拦截以后端 403 为准——
 * 授权可能在 GET /me 与 PATCH /me/settings 之间失效，所以 save() 里另有一条 403 分支。
 */
function isPossiblyUnder14(birthYear) {
  if (typeof birthYear !== 'number') return false
  return new Date().getFullYear() - birthYear <= 14
}

/** 监护人状态 → 拦截原因；null = 不拦。区分「从没确认/待确认」与「已失效」，对应两个不同的 403 code。 */
function guardianBlockKind(status) {
  if (status === 'active') return null
  if (status === 'expired' || status === 'revoked') return 'expired'
  return 'required'
}

function UserContentEmbeddingConsent({ item, value, available, pageDisabled, onSaved }) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  const [rowError, setRowError] = useState(null)
  const [profile, setProfile] = useState(null)

  // 后端还没这个 key 时不必去读资料：开关反正点不动，也就没有「未成年能否开」要判
  useEffect(() => {
    if (!available) return undefined
    let cancelled = false
    getMe()
      .then((d) => {
        if (!cancelled) setProfile(d)
      })
      .catch(() => {
        /* 读不到资料就按「不拦」处理，交给后端 403 兜底 */
      })
    return () => {
      cancelled = true
    }
  }, [available])

  // pending：后端尚未落地该字段。置灰 + 说明，且不会发任何请求。
  const pending = !available
  const blockKind = profile ? guardianBlockKind(profile.guardianAuthorization?.status) : null
  const needGuardian = isPossiblyUnder14(profile?.birthYear) && blockKind !== null
  const blockedByServer = rowError?.kind === 'required' || rowError?.kind === 'expired'
  const locked = (needGuardian || blockedByServer) && !value
  const hint = pending
    ? '该功能正在接入中：后端就绪后这里会自动可用。'
    : (rowError?.text ?? (locked ? GUARDIAN_HINT[blockKind ?? 'required'] : null))

  const save = async (next) => {
    setBusy(true)
    setConfirmError('')
    setRowError(null)
    try {
      const data = await updateSettings({ [UCE_KEY]: next })
      onSaved(toSettingsValues(data))
      setConfirmOpen(false)
    } catch (err) {
      if (err?.code === GUARDIAN_REQUIRED || err?.code === GUARDIAN_EXPIRED) {
        const kind = err.code === GUARDIAN_EXPIRED ? 'expired' : 'required'
        setRowError({ kind, text: err?.message || GUARDIAN_HINT[kind] })
        // 只有「开启」被拒才关窗；撤回（false）按契约不该走到这个分支
        if (next) setConfirmOpen(false)
      } else if (isNetworkError(err)) {
        const text = '设置服务暂不可用，请稍后再试'
        if (next) setConfirmError(text)
        else setRowError({ kind: 'save', text })
      } else {
        const text = err?.message ?? '保存失败，请稍后再试'
        if (next) setConfirmError(text)
        else setRowError({ kind: 'save', text })
      }
    } finally {
      setBusy(false)
    }
  }

  const handleChange = (checked) => {
    setRowError(null)
    if (pending) return // 后端还没这个 key，不发请求（也不该发）
    if (!checked) {
      save(false) // 撤回是用户权利：任何授权状态下都必须能关掉
      return
    }
    if (locked) {
      const kind = blockKind ?? 'required'
      setRowError({ kind, text: GUARDIAN_HINT[kind] })
      return
    }
    setConfirmError('')
    setConfirmOpen(true) // 不是点开关就直接生效：先弹窗，再由用户二次确认
  }

  const handleConfirm = () => {
    if (!busy) save(true)
  }

  const handleCancel = () => {
    if (busy) return
    setConfirmOpen(false)
    setConfirmError('')
  }

  return (
    <>
      <div className={styles.item}>
        <div className={styles.itemBody}>
          <h2 className={styles.itemTitle}>
            {item.title}
            <span className={styles.defaultTag}>默认关闭</span>
          </h2>
          <p className={styles.itemDesc}>{item.description}</p>
          {hint ? (
            <p className={pending ? styles.consentPending : styles.consentHint}>{hint}</p>
          ) : null}
        </div>
        <div className={styles.switchWrap}>
          <Switch
            checked={value}
            loading={busy}
            disabled={pageDisabled || pending || locked}
            onChange={handleChange}
          />
        </div>
      </div>

      <Modal
        open={confirmOpen}
        title="开启「内容向量化使用第三方服务」？"
        okText="确认开启"
        cancelText="再想想"
        okButtonProps={{ loading: busy }}
        cancelButtonProps={{ disabled: busy }}
        onOk={handleConfirm}
        onCancel={handleCancel}
        destroyOnClose
      >
        <div className={styles.consentBody}>
          <p className={styles.consentLead}>开启后会发生这三件事：</p>
          <ul className={styles.consentList}>
            <li>
              <b>发送什么</b>：你在错题里写的题干原文、你的作答内容，以及学习记录里的文字。
            </li>
            <li>
              <b>发给谁</b>：受信任的第三方向量化服务。它只把这些内容转换成检索用的向量，不做其它用途。
            </li>
            <li>
              <b>换来什么</b>：语义检索更准，复习时更容易找到「问法不同、意思相近」的题。
            </li>
          </ul>
          <p className={styles.consentNote}>
            保持关闭时，这些内容只在本机用本地模型处理，不会发送；本地模型不可用时检索会退回到字面匹配，
            找得没那么准，但仍然不会发送。开启之后你也可以随时关掉。
          </p>
          <p className={styles.consentLegal}>本产品由学生团队开发，上述文案未经专业法律审核。</p>
          {confirmError ? <p className={styles.consentError}>{confirmError}</p> : null}
        </div>
      </Modal>
    </>
  )
}


// ===== 账号与资料 =====

function AccountPanel() {
  const { user } = useAuth()
  const [profile, setProfile] = useState(null)

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((d) => { if (!cancelled) setProfile(d) })
      .catch(() => { /* 资料读不到不影响设置页其它部分 */ })
    return () => { cancelled = true }
  }, [])

  return (
    <section className={styles.card}>
      <div className={styles.item}>
        <div className={styles.itemBody}>
          <h2 className={styles.itemTitle}>账号邮箱</h2>
          <p className={styles.itemDesc}>{user?.email ?? '（未登录）'}</p>
        </div>
      </div>
      <div className={styles.item}>
        <div className={styles.itemBody}>
          <h2 className={styles.itemTitle}>资料建档</h2>
          <p className={styles.itemDesc}>
            {profile
              ? `学段 ${profile.stage === 'junior' ? '初中' : '高中'} · 年级 ${profile.grade || '—'} · 出生年份 ${profile.birthYear ?? '未填写'}`
              : '读取中…'}
          </p>
        </div>
        <Link className={styles.inlineBtn} to="/profile-setup">去修改</Link>
      </div>
    </section>
  )
}


// ===== 匿名群体参照授权面板（板块三 M4，决策 v1.7 §4.10 + D41 授权前置） =====

function CommunityConsentPanel() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [needGuardian, setNeedGuardian] = useState(false);

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
    setNeedGuardian(false);
    try {
      const d = await putCommunityConsent(checked, checked ? true : undefined);
      setEnabled(d.enabled);
    } catch (e) {
      // D41：未授权 / 授权失效时后端返回 403，把用户引到本页下方的「监护人授权」卡片
      if (e?.code === 'GUARDIAN_AUTHORIZATION_REQUIRED' || e?.code === 'GUARDIAN_AUTHORIZATION_EXPIRED') {
        setNeedGuardian(true);
        setErr(e.message || '需要先完成监护人授权');
      } else {
        setErr(isNetworkError(e) ? '服务暂不可用，请稍后再试' : (e?.message ?? '保存失败'));
      }
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
      {err ? (
        <p className={styles.error}>
          {err}
          {needGuardian ? ' 请先在下方「监护人授权」完成确认后再开启。' : ''}
        </p>
      ) : null}
    </section>
  );
}

// ===== AI 调权面板（PRD 5.2 / 6.5） =====
// ⚠️ D42 已定：引擎权重调参**移出用户产品**（去处见目标态 §4.7.2），下线归 E 板块 M4。
// 本面板保留至 E 下线；它不在 A 板块的「授权与隐私」子页里。

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

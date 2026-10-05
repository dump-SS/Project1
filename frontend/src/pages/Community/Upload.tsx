/**
 * 模块三 · 页面 1：群体参照入口页（/community）
 * ------------------------------------------------------------
 * M4 转正（决策 v1.7 §4.11 / §4.7）后的口径变化：
 * **服务端每周自动抽取是唯一真源，客户端不上传任何特征值**。
 * 因此本页不再有"填写 + 保存我的本周数据"表单，也不再写 localStorage
 * （`community_pool` / `community_my_data` 随 `community.ts` 一并下线）——
 * 那两个键正是"假人数据"的来源，留着就会与真聚合形成双轨。
 *
 * 本页现在承担两件事：
 * 1. 讲清楚参与方式（授权 → 服务端匿名抽取 → 只读聚合，撤回即删除）；
 * 2. 作为授权状态与对比页的入口（含开启动作，其两个监护人授权 403 分别提示）。
 *
 * 数据源：GET/PUT /me/community-consent（services/communityApi.ts）。
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import styles from './index.module.css'
import { ApiError } from '../../services/http'
import {
  fetchCommunityConsent,
  putCommunityConsent,
  type CommunityConsent,
} from '../../services/communityApi'

/** 开启动作的失败原因：两个监护人授权 403 与其它错误分开呈现 */
type EnableError = { code?: string; text: string; toPrivacy: boolean }

function describeEnableError(err: unknown): EnableError {
  const code = err instanceof ApiError ? err.code : undefined
  if (code === 'GUARDIAN_AUTHORIZATION_REQUIRED') {
    return {
      code,
      text: '开启群体参照需要先完成监护人授权（未满 14 岁强制）。请前往「设置 → 授权与隐私」完成监护人确认后再回来开启。',
      toPrivacy: true,
    }
  }
  if (code === 'GUARDIAN_AUTHORIZATION_EXPIRED') {
    return {
      code,
      text: '监护人授权已失效（已过期或已撤回），需要重新确认授权后才能开启群体参照。',
      toPrivacy: true,
    }
  }
  return {
    code,
    text: err instanceof Error && err.message ? err.message : '开启失败，请稍后再试。',
    toPrivacy: false,
  }
}

export default function CommunityUploadPage() {
  /** null = 读取中或读取失败（不把"读不到"当成"已开启"） */
  const [consent, setConsent] = useState<CommunityConsent | null>(null)
  const [consentError, setConsentError] = useState(false)
  const [enabling, setEnabling] = useState(false)
  const [enableError, setEnableError] = useState<EnableError | null>(null)

  const load = () => {
    setConsentError(false)
    fetchCommunityConsent()
      .then((d) => setConsent(d))
      .catch(() => { setConsent(null); setConsentError(true) })
  }

  useEffect(() => { load() }, [])

  const handleEnable = async () => {
    setEnabling(true)
    setEnableError(null)
    try {
      const next = await putCommunityConsent(true)
      setConsent(next)
    } catch (e) {
      setEnableError(describeEnableError(e))
    } finally {
      setEnabling(false)
    }
  }

  const handleRevoke = async () => {
    setEnabling(true)
    setEnableError(null)
    try {
      // 撤回不受监护人授权状态限制（撤回是用户权利，不能被授权失效挡住）
      const next = await putCommunityConsent(false)
      setConsent(next)
    } catch (e) {
      setEnableError(describeEnableError(e))
    } finally {
      setEnabling(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <header className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>匿名群体对比</h1>
          <p className={styles.pageSubtitle}>
            不记名、不关联账号。你的学习特征由服务端匿名抽取，只用于生成同龄群体的聚合分布。
          </p>
        </header>

        {/* 授权状态：决定本页显示什么 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>授权状态</h2>

          {consent === null && !consentError && (
            <p className={styles.privacyNote}>正在读取授权状态…</p>
          )}

          {consent === null && consentError && (
            <>
              <p className={styles.emptyText}>没能读到授权状态，请检查登录状态后重试。</p>
              <button type="button" className={styles.linkBtn} onClick={load}>重新读取</button>
            </>
          )}

          {consent?.enabled === false && (
            <>
              <p className={styles.privacyNote}>
                尚未开启匿名聚合授权。开启后，你每周的学习特征（时长 / 专注 / 疲劳 / 完成率）
                将由服务端匿名抽取并进入同龄群体的聚合统计；随时可以撤回，撤回即删除已抽取的特征。
              </p>
              <button
                type="button"
                className={styles.submitBtn}
                disabled={enabling}
                onClick={handleEnable}
              >
                {enabling ? '正在开启…' : '开启匿名聚合授权'}
              </button>
              {enableError && <p className={styles.privacyNote}>{enableError.text}</p>}
              {enableError?.toPrivacy && (
                <Link to="/settings?tab=privacy" className={styles.linkBtn}>前往授权与隐私 →</Link>
              )}
              <p className={styles.privacyNote}>
                未满 14 岁需先完成监护人授权；开启前不会上传你的任何数据。
              </p>
            </>
          )}

          {consent?.enabled === true && (
            <>
              <p className={styles.privacyNote}>
                已开启匿名聚合授权。特征由服务端每周自动匿名抽取，客户端不上传任何数据。
                撤回后你的全部特征行会被物理删除，并在下一次聚合重算后退出统计。
              </p>
              <div className={styles.actions}>
                <Link to="/community/compare" className={styles.linkBtn}>查看群体对比 →</Link>
                <button
                  type="button"
                  className={styles.linkBtnGhost}
                  disabled={enabling}
                  onClick={handleRevoke}
                >
                  {enabling ? '处理中…' : '撤回授权'}
                </button>
              </div>
              {enableError && <p className={styles.privacyNote}>{enableError.text}</p>}
            </>
          )}
        </section>

        {/* 参与方式说明：把"为什么不让你填表"讲清楚 */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>参与方式</h2>
          <div className={styles.myGrid}>
            <div className={styles.myItemHead}>
              <span>数据来源</span>
              <span className={styles.myValue}>服务端自动抽取</span>
            </div>
            <div className={styles.myItemHead}>
              <span>页面上传</span>
              <span className={styles.myValue}>不需要</span>
            </div>
            <div className={styles.myItemHead}>
              <span>最小样本</span>
              <span className={styles.myValue}>不足则不展示</span>
            </div>
            <div className={styles.myItemHead}>
              <span>撤回方式</span>
              <span className={styles.myValue}>设置 → 授权与隐私</span>
            </div>
          </div>
          <p className={styles.privacyNote}>
            为避免"手工填报"污染统计，本项目不提供特征上传入口：你不需要填写任何数值，
            页面上的对比结果全部来自服务端聚合，且只在参与人数足够时才会展示。
          </p>
        </section>

        <p className={styles.pageFooter}>everyone studies at their own pace.</p>
      </div>
    </div>
  )
}

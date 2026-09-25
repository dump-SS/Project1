import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInView } from '../../hooks/useInView'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CTA_COPY, FOOTER_COPY, HERO_ACTIONS, HERO_DRAFT_KEY } from '../../content/copy'
import { IconArrowUp } from '../../icons/UiIcons'
import styles from './CtaFooter.module.css'

/**
 * CTA + 页尾（visual-language §7.8）：
 * - 末句英文滑到底翻转：Nothing, without you. → You're everything.（与光变亮同一拍）；
 * - 页尾 = 全站唯一「大面积 + 鲜明 + 流体渐变」特例区（无正文要读，放开强度）；
 * - Grainient 懒加载（接近视口才取 landing-gfx chunk）；reduced-motion → 静态渐变兜底；
 * - 占位规则：链接地址/备案/版权年份——结构留位、内容留空，不预先编造；
 * - 合规硬项：「学生团队开发，未经专业法律审核」显著标注。
 */

// 重依赖（ogl）只随本组件的动态 chunk 加载，首屏不取
const Grainient = lazy(() => import('../bits/Grainient'))

export default function CtaFooter() {
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [atBottom, setAtBottom] = useState(false) // 句子翻转 + 光变亮（同一拍）
  const ctaRef = useRef<HTMLDivElement>(null)

  /* 接近页尾才拉 Grainient chunk（进入视口前 40%） */
  const [gfxRef, gfxNear] = useInView<HTMLDivElement>('40% 0px', true)

  /* 滑到最底部：句子翻转与光变亮同一个拍子（整页唯一可爆发情绪处） */
  useEffect(() => {
    const onScroll = () => {
      const reach = window.scrollY + window.innerHeight
      const bottom = document.documentElement.scrollHeight
      setAtBottom(reach >= bottom - 8)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  /* 草稿跨登录墙（与 Hero 同一存储 key） */
  useEffect(() => {
    const saved = localStorage.getItem(HERO_DRAFT_KEY)
    if (saved) setDraft(saved)
  }, [])

  const onDraftChange = (v: string) => {
    setDraft(v)
    localStorage.setItem(HERO_DRAFT_KEY, v)
  }

  return (
    <>
      {/* ---------- 上部：末句 + 输入框（暗区） ---------- */}
      <section className={styles.cta} aria-label="开始使用" ref={ctaRef}>
        <div className={`${styles.ctaInner} landing-wrap`}>
          {/* 末句翻转（不加中文小字对照——短句的力在短） */}
          <p className={styles.finalLine} aria-live="polite">
            <span className={atBottom ? styles.lineOut : ''}>{CTA_COPY.before}</span>
            <span className={atBottom ? styles.lineIn : styles.lineHidden} aria-hidden={!atBottom}>
              {CTA_COPY.after}
            </span>
          </p>

          <input
            className={styles.input}
            type="text"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigate('/login')
            }}
            placeholder={HERO_ACTIONS.inputPlaceholder}
            aria-label={HERO_ACTIONS.inputPlaceholder}
          />
        </div>
      </section>

      {/* ---------- 下部：页尾（亮区流体渐变特例） ---------- */}
      <footer className={styles.footer} id="landing-footer" ref={gfxRef}>
        {/* 流体渐变背景：鲜明、流动、指针交互（Grainient 落盘版） */}
        <div className={styles.bg} aria-hidden>
          {gfxNear && !reduced && (
            <Suspense fallback={<div className={styles.bgFallback} />}>
              <Grainient
                lightMode
                color1="#4AD1FF"
                color2="#1B5DBF"
                color3="#8FD3E8"
                timeSpeed={atBottom ? 0.55 : 0.22}
                zoom={atBottom ? 1.06 : 0.92} /* 光变亮与句子翻转同一拍 */
                contrast={1.25}
                grainAmount={0.06}
                warpSpeed={atBottom ? 3.4 : 2.0}
              />
            </Suspense>
          )}
          {(reduced || !gfxNear) && <div className={styles.bgFallback} />}
          {/* 暗色 scrim：保页尾文字对比度 ≥ 4.5:1（页尾加深遮罩，不切文字颜色） */}
          <div className={styles.bgScrim} />
        </div>

        <div className={`${styles.footerInner} landing-wrap`}>
          {/* 品牌 logo + 一句话简介 */}
          <div className={styles.brandCol}>
            <img
              src="/brand/logo-full-on-light-trim.png"
              alt="EpochX"
              height={36}
              className={styles.footerLogo}
            />
            <p className={styles.tagline}>{FOOTER_COPY.tagline}</p>
          </div>

          {/* 链接组：结构留位、内容留空（占位规则——不预先编造链接地址） */}
          <nav className={styles.links} aria-label="页脚链接">
            {FOOTER_COPY.links.map((label) => (
              /* TODO(上线前)：真实链接地址统一确认后填入（Skyer 占位规则） */
              <span key={label} className={styles.linkPlaceholder}>
                {label}
              </span>
            ))}
          </nav>

          {/* 返回顶部 */}
          <button
            type="button"
            className={styles.backTop}
            onClick={() => window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })}
          >
            {FOOTER_COPY.backToTop}
            <IconArrowUp size={15} />
          </button>
        </div>

        {/* 版权行（年份留空）+ 备案占位行 */}
        <div className={`${styles.legal} landing-wrap`}>
          <p>
            {FOOTER_COPY.copyrightPrefix}
            {/* TODO(上线前)：版权年份确认后填入 */}
            <span className={styles.blank} />
            {' '}EpochX
          </p>
          {/* TODO(上线前)：ICP/网安备案信息确认后填入 */}
          <p className={styles.blankRow}>&nbsp;</p>
          {/* 合规硬项：显著标注 */}
          <p className={styles.compliance}>{FOOTER_COPY.compliance}</p>
        </div>
      </footer>
    </>
  )
}

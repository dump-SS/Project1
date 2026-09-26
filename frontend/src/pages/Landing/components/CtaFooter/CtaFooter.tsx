import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInView } from '../../hooks/useInView'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CTA_COPY, FOOTER_COPY, HERO_ACTIONS, HERO_DRAFT_KEY } from '../../content/copy'
import { IconArrowUp, IconSend } from '../../icons/UiIcons'
import GlareHover from '../bits/GlareHover'
import GradualBlur from '../bits/GradualBlur'
import FoldText from '../bits/FoldText'
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

/** 末句渐变（Skyer 2026-09-25：后一句用 bits Gradient Text 的配色）：
 *  为保深底可读，去掉最深的 #1B5DBF 一档，留住亮青 → 品牌蓝 */
const FINAL_LINE_GRADIENT = ['#8FD3E8', '#4AD1FF', '#3AA0E8'] as const

export default function CtaFooter() {
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [atBottom, setAtBottom] = useState(false) // 句子翻转 + 光变亮（同一拍）
  const ctaRef = useRef<HTMLDivElement>(null)
  /** 渐隐带上沿锚点：分割线（Skyer 2026-09-25：从分割线就开始渲染，而不是从输入框/卡片） */
  const dividerRef = useRef<HTMLDivElement>(null)
  /** 渐隐带宿主：固定在视口底边，高度由 JS 按分割线位置逐帧写（不触发 React 重渲染） */
  const bandRef = useRef<HTMLDivElement>(null)

  /* 接近页尾才拉 Grainient chunk（进入视口前 40%） */
  const [gfxRef, gfxNear] = useInView<HTMLDivElement>('40% 0px', true)

  /* 滑到最底部：句子翻转与光变亮同一个拍子（整页唯一可爆发情绪处）
     + 页底渐隐带（三段行为，Skyer 2026-09-25 三次校准）：
       ① 滚动中：上沿跟着**分割线**走（分割线还在视口底部时带子很薄，随它上移逐渐长到视口底）
          ——「从分割线就开始渲染」，刚滚进来的内容一进画面就落在带子的渐变里；
       ② 停止滚动 180ms 后：上沿**收回到合规声明底部之下**（320ms 缓动）——静止时页脚
          logo/链接/版权/合规声明全部清晰，只留卡片下半的柔和渐隐；
       ③ 分割线在视口外时带子为零高，不打扰上面的屏。
     高度直接写 DOM（逐帧不触发 React 重渲染）；只在「收回」那一次挂 transition。 */
  useEffect(() => {
    let settleTimer = 0
    const legalEl = () => document.querySelector('#landing-footer p:last-child')
    const bandFloor = (vh: number) => {
      const lg = legalEl()
      return (lg ? lg.getBoundingClientRect().bottom : vh * 0.4) + 24
    }
    const setBandTop = (vh: number, top: number) => {
      const band = bandRef.current
      if (band) band.style.height = `${Math.max(0, vh - top).toFixed(1)}px`
    }
    const onScroll = () => {
      const vh = window.innerHeight
      const reach = window.scrollY + vh
      setAtBottom(reach >= document.documentElement.scrollHeight - 8)

      const band = bandRef.current
      const divider = dividerRef.current
      if (!band || !divider) return
      // ① 滚动中：跟分割线（0 上限 → 分割线仍在视口底部时带子渐长）
      band.style.transition = 'none'
      setBandTop(vh, Math.min(vh, Math.max(0, divider.getBoundingClientRect().top)))
      // ② 停稳后收回到下限
      window.clearTimeout(settleTimer)
      settleTimer = window.setTimeout(() => {
        const b = bandRef.current
        const d = dividerRef.current
        if (!b) return
        const nowVh = window.innerHeight
        const top = Math.min(nowVh, Math.max(bandFloor(nowVh), d ? d.getBoundingClientRect().top : nowVh))
        b.style.transition = 'height 320ms ease-out'
        setBandTop(nowVh, top)
      }, 180)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    onScroll()
    return () => {
      window.clearTimeout(settleTimer)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
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
      {/* ---------- 图标海 → CTA 的分割线（Skyer 2026-09-25）----------
          通栏（左右顶到屏幕边缘）：直接作为 main 的子元素铺满视口宽，不套内容栏。
          同时充当页底渐隐带的上沿锚点（见 bandRef）。 */}
      <div className={styles.divider} ref={dividerRef} aria-hidden />

      {/* ---------- 上部：末句 + 输入框（暗区，2026-09-25 Skyer 重排：紧凑、上移） ---------- */}
      <section className={styles.cta} aria-label="开始使用" ref={ctaRef}>
        <div className={`${styles.ctaInner} landing-wrap`}>
          {/* 末句：衬线（两句都改）；滑到底翻转——首句淡出、后句「折入」+ 渐变字 */}
          <p className={styles.finalLine} aria-live="polite">
            <span className={atBottom ? styles.lineOut : ''}>{CTA_COPY.before}</span>
            <span
              className={`${styles.lineIn} ${atBottom ? '' : styles.lineHidden}`}
              aria-hidden={!atBottom}
            >
              {atBottom && (
                <FoldText
                  text={CTA_COPY.after}
                  splitBy="char"
                  hinge="top"
                  duration={0.5}
                  stagger={0.03}
                  delay={0.2} /* 让首句先淡出，避免两句叠在一起那一瞬 */
                  creaseShading={0.5}
                  fontSize="clamp(28px, 4.4vw, 52px)"
                  fontWeight={500}
                  gradientColors={FINAL_LINE_GRADIENT}
                  className={styles.foldLine}
                />
              )}
            </span>
          </p>

          {/* 输入胶囊（与 Hero 同款）+ Glare Hover（hover 光泽扫过）+ 右侧圆形发送键 */}
          <GlareHover
            width="min(560px, 100%)" /* 尺寸走组件内联 width（类里写会被内联覆盖） */
            height="56px"
            background="rgba(27, 34, 45, 0.72)"
            borderColor="rgba(140, 160, 180, 0.16)"
            borderRadius="999px"
            glareColor="#BFE9FF"
            glareOpacity={0.22}
            glareSize={180}
            transitionDuration={700}
            className={styles.inputGlare}
            style={{ cursor: 'text' }}
          >
            <div className={styles.inputRow}>
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
              <button
                type="button"
                className={styles.sendBtn}
                onClick={() => navigate('/login')}
                aria-label="发送"
              >
                <IconSend size={17} />
              </button>
            </div>
          </GlareHover>
        </div>
      </section>

      {/* ---------- 下部：页尾（亮区流体渐变特例） ----------
          2026-09-25 Skyer：动效区左右留空 + 上两角大圆角，页底 Gradual Blur 渐隐 */}
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

      {/* 页底渐隐（React Bits GradualBlur，Skyer 2026-09-25 三次指定）：
          **上沿跟着分割线走**——宿主固定在视口底边、高度由滚动处理器逐帧写（分割线还在
          视口底部时带子很薄，随它上移逐渐长到视口底），所以「从分割线就开始渲染」：刚滚
          进来的内容（分割线本身、末句、输入框、卡片……）一进画面就落在带子的渐变里。
          上沿有下限保护（合规声明底部之下），静止时页脚文字全部保持清晰。
          z-index 100：压过页尾内容、低于顶栏面板。
          ⚠️ 性能：固定全宽 backdrop-filter 层数/半径决定合成成本，实测 7 层/末层 96px 时
          预览连截图都准备不出来。这里 3 层 / 上限约 30px（层值 blur(3.9)/blur(14.9)/blur(30.4px)）。
          ⚠️ 组件层用 Tailwind `inset-0` 定尺，本页没引 theme → 该声明失效、层会变 0×0
          （backdrop-filter 无从作用 =「完全看不到」）；尺寸由 landing.css 的补丁补回。 */}
      {!reduced && (
        <div className={styles.blurHost} ref={bandRef} aria-hidden>
          <GradualBlur
            preset="bottom"
            height="100%"
            strength={1.9}
            divCount={3}
            exponential
            curve="bezier"
            zIndex={0}
          />
        </div>
      )}
    </>
  )
}

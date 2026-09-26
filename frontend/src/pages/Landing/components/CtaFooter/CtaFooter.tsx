import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { HERO_DRAFT_KEY } from '../../content/copy'
import { useCopy } from '../../content/i18n'
import { IconArrowUp, IconSend } from '../../icons/UiIcons'
import GlareHover from '../bits/GlareHover'
import GradualBlur from '../bits/GradualBlur'
import FoldText from '../bits/FoldText'
import GlassSurface from '../bits/GlassSurface'
import styles from './CtaFooter.module.css'

/**
 * CTA + 页尾（visual-language §7.8）：
 * - 末句英文滑到底翻转：Nothing, without you. → You're everything.（与光变亮同一拍）；
 * - 页尾 = 全站唯一「大面积 + 鲜明 + 流体渐变」特例区（无正文要读，放开强度）；
 * - 背景 = Iridescence（2026-09-25 Skyer 指定，替换原 Grainient）：懒加载（接近视口才取
 *   landing-gfx chunk）；reduced-motion → 静态帧 + 静态渐变兜底；
 * - 占位规则：链接地址/备案/版权年份——结构留位、内容留空，不预先编造；
 * - 合规硬项：「学生团队开发，未经专业法律审核」显著标注。
 */

// 重依赖（ogl）只随本组件的动态 chunk 加载，首屏不取
const Iridescence = lazy(() => import('../bits/Iridescence'))

/** 末句渐变（Skyer 2026-09-25：后一句用 bits Gradient Text 的配色）：
 *  为保深底可读，去掉最深的 #1B5DBF 一档，留住亮青 → 品牌蓝 */
const FINAL_LINE_GRADIENT = ['#8FD3E8', '#4AD1FF', '#3AA0E8'] as const

/** Iridescence 基色（乘在 shader 输出上的 0–1 分量）：
 *  带一点蓝品牌倾向的亮色——全白会偏「彩虹纸」，压蓝后仍是虹彩但落在品牌色域；
 *  乘完每通道仍在 0.46–1，配合 .bgScrim 保深色文字对比度。 */
const IRIDESCENCE_COLOR: [number, number, number] = [0.86, 0.95, 1]

export default function CtaFooter() {
  const reduced = useReducedMotion()
  const c = useCopy()
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [atBottom, setAtBottom] = useState(false) // 句子翻转 + 光变亮（同一拍）
  /** 页底渐隐带是否渲染：分割线一滚进视口就开（Skyer 2026-09-25 最终口径） */
  const [bandOn, setBandOn] = useState(false)
  const ctaRef = useRef<HTMLDivElement>(null)
  /** 分割线：渐隐带渲染时机的参照（带子本身高度固定，不随它变） */
  const dividerRef = useRef<HTMLDivElement>(null)
  /** 末句：与分割线一起取中点，作为渐隐带的触发位置（Skyer 2026-09-25） */
  const lineRef = useRef<HTMLParagraphElement>(null)
  /** reduced-transparency：玻璃胶囊退纯色底（dev-spec §6；与顶栏同一处理） */
  const [reduceTransparency, setReduceTransparency] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-transparency: reduce)')
    const on = () => setReduceTransparency(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  /** 渐隐带宿主（固定高度见 CSS，只切换渲染开关） */
  const bandRef = useRef<HTMLDivElement>(null)

  /* 接近页尾才拉 Grainient chunk（进入视口前 40%） */

  /* 滑到最底部：句子翻转与光变亮同一个拍子（整页唯一可爆发情绪处）
     + 页底渐隐带（Skyer 2026-09-25 四次校准，最终口径）：
       **带子高度固定不变**（30vh，见 .blurHost），**触发点取「分割线」与「末句」的中点**
       （Skyer 2026-09-25：不要卡在分割线处触发，往下挪到两者之间）——中点进入视口即点亮
       （淡入 0.4s，滚回去自动熄灭）。取中点而非写死偏移量，留白改了也不会失准。
       上沿固定在距视口底 30vh 处，正好落在页脚文字（logo/链接/版权/合规声明）下方，
       所以静止时文字全部清晰，只有卡片下半的空白渐变是软的。 */
  useEffect(() => {
    const onScroll = () => {
      const vh = window.innerHeight
      const reach = window.scrollY + vh
      setAtBottom(reach >= document.documentElement.scrollHeight - 8)
      const divider = dividerRef.current
      const line = lineRef.current
      if (!divider || !line) return
      const mid =
        (divider.getBoundingClientRect().top + line.getBoundingClientRect().top) / 2
      setBandOn(mid < vh)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    onScroll()
    return () => {
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
      <section className={styles.cta} aria-label={c.a11y.cta} ref={ctaRef}>
        <div className={`${styles.ctaInner} landing-wrap`}>
          {/* 末句：衬线（两句都改）；滑到底翻转——首句淡出、后句「折入」+ 渐变字 */}
          <p className={styles.finalLine} aria-live="polite" ref={lineRef}>
            <span className={atBottom ? styles.lineOut : ''}>{c.cta.before}</span>
            <span
              className={`${styles.lineIn} ${atBottom ? '' : styles.lineHidden}`}
              aria-hidden={!atBottom}
            >
              {atBottom && (
                <FoldText
                  text={c.cta.after}
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
            glareOpacity={0.12} /* 生硬→柔（0.22 → 0.12，光泽更淡） */
            glareSize={260} /* 光带更宽更柔（180 → 260） */
            transitionDuration={420} /* 偏慢→利落（700ms → 420ms） */
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
                placeholder={c.heroActions.inputPlaceholder}
                aria-label={c.heroActions.inputPlaceholder}
              />
              <button
                type="button"
                className={styles.sendBtn}
                onClick={() => navigate('/login')}
                aria-label={c.a11y.sendMessage}
              >
                <IconSend size={17} />
              </button>
            </div>
          </GlareHover>
        </div>
      </section>

      {/* ---------- 下部：页尾（亮区流体渐变特例） ----------
          2026-09-25 Skyer：动效区左右留空 + 上两角大圆角，页底 Gradual Blur 渐隐 */}
      <footer className={styles.footer} id="landing-footer">
        {/* 虹彩背景：鲜明、流动、指针交互（Iridescence 落盘版；2026-09-25 替换 Grainient）
            ⚠️ **不再用 `gfxNear` 门控渲染**（Skyer 2026-09-25「Iridescence 没了」）：
            该门控依赖 IntersectionObserver，实测出现过不置位的情况，此时渲染的是
            `.bgFallback`（同为淡青/淡紫渐变），观感就是「虹彩变淡甚至没有」。而门控
            本来只为「晚点取 chunk」——ogl 早被 Hero 的 Prism 拉过（同一 chunk），
            且组件自身已有离屏暂停，故直接挂载、由 Suspense 兜住加载瞬间。 */}
        <div className={styles.bg} aria-hidden>
          <Suspense fallback={<div className={styles.bgFallback} />}>
            <Iridescence
              color={IRIDESCENCE_COLOR}
              /* 滑到底「光变亮」与句子翻转同一拍：提速（相位用积分实现，提速不断相位） */
              speed={atBottom ? 0.85 : 0.32}
              amplitude={0.12}
              staticFrame={reduced} /* reduced-motion：只渲染静止一帧 */
              className={styles.bgCanvas}
            />
          </Suspense>
          {/* 浅色 scrim：保页尾文字对比度 ≥ 4.5:1（压到刚好够用，尽量让虹彩透出来） */}
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
            <p className={styles.tagline}>{c.footer.tagline}</p>
          </div>

          {/* 链接组：结构留位、内容留空（占位规则——不预先编造链接地址） */}
          <nav className={styles.links} aria-label={c.a11y.footerLinks}>
            {c.footer.links.map((link) => (
              /* TODO(上线前)：真实链接地址统一确认后填入（Skyer 占位规则）。
                 母项可带子项（2026-09-27：隐私协议 / 用户协议挂到服务条款下）；
                 一律 span 不可点击，hover 只做下划线生长 + 文字高亮。 */
              <div key={link.name} className={styles.linkGroup}>
                <span className={`${styles.linkPlaceholder} ${styles.linkParent}`}>{link.name}</span>
                {link.children?.length ? (
                  <div className={styles.linkSubList}>
                    {link.children.map((child) => (
                      <span key={child} className={`${styles.linkPlaceholder} ${styles.linkSub}`}>
                        {child}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </nav>

          {/* 返回顶部：GlassSurface 胶囊（Skyer 2026-09-25）。
              玻璃层是绝对定位的兄弟节点，文字/图标必须各自带 position+z-index 才压得住
              （裸文本节点无法定层，会被玻璃层盖住）。reduced-transparency → 纯色底。 */}
          <button
            type="button"
            className={styles.backTop}
            onClick={() => window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })}
          >
            <span className={styles.backTopGlass} aria-hidden>
              {reduceTransparency ? (
                <span className={styles.backTopSolid} />
              ) : (
                <GlassSurface
                  width="100%"
                  height="100%"
                  borderRadius={999}
                  backgroundOpacity={0.34}
                  blur={14}
                  saturation={1.3}
                  className={styles.glassPill}
                  style={{ position: 'absolute', inset: 0 }}
                />
              )}
            </span>
            <span className={styles.backTopLabel}>{c.footer.backToTop}</span>
            <IconArrowUp size={15} className={styles.backTopIcon} />
          </button>
        </div>

        {/* 版权行（权利人 + 年份已定：未名_Official 2026）*/}
        <div className={`${styles.legal} landing-wrap`}>
          <p>
            {c.footer.copyrightPrefix}
            {c.footer.copyrightHolder} {c.footer.copyrightYear}
          </p>
          {/* TODO(上线前)：ICP/网安备案信息确认后填入 */}
          <p className={styles.blankRow}>&nbsp;</p>
          {/* 合规硬项：显著标注 */}
          <p className={styles.compliance}>{c.footer.compliance}</p>
        </div>
      </footer>

      {/* 页底渐隐（React Bits GradualBlur，Skyer 2026-09-25 四次校准后的最终口径）：
          **高度固定不变**（30vh，见 .blurHost），**分割线一滚进视口就开始渲染**
          （淡入 0.4s）——从下方滚进来的内容（末句、输入框、卡片、logo……）经过这条
          固定高度的带子时是糊的，滚出带子即变清晰；滚回图标海自动熄灭。
          z-index 100：压过页尾内容、低于顶栏面板。
          ⚠️ 性能：固定全宽 backdrop-filter 层数/半径决定合成成本（实测 7 层/末层 96px
          时预览连截图都准备不出来）。这里 3 层 / 上限约 30px。
          ⚠️ 组件层用 Tailwind `inset-0` 定尺，本页没引 theme → 该声明失效、层会变 0×0
          （backdrop-filter 无从作用 =「完全看不到」）；尺寸由 landing.css 的补丁补回。 */}
      {!reduced && (
        <div
          className={`${styles.blurHost} ${bandOn ? styles.blurHostOn : ''}`}
          ref={bandRef}
          aria-hidden
        >
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

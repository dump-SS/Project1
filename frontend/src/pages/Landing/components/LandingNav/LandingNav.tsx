import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { NAV_COPY } from '../../content/copy'
import { getHijackRange, subscribeHijack } from '../../lib/navScrollGuard'
import GlassSurface from '../bits/GlassSurface'
import styles from './LandingNav.module.css'

type MenuKey = 'product' | 'pricing' | 'resources' | null

interface PanelDef {
  readonly lead: string
  readonly items: ReadonlyArray<{ readonly name: string; readonly href: string }>
}

const PANELS: Record<Exclude<MenuKey, null>, PanelDef | null> = {
  product: NAV_COPY.productPanel,
  pricing: null, // 定价无展开面板，选项后带灰描边「暂无」标签
  resources: NAV_COPY.resourcesPanel,
}

export default function LandingNav() {
  const { status } = useAuth()
  const [openMenu, setOpenMenu] = useState<MenuKey>(null)
  const [scrolledPastHero, setScrolledPastHero] = useState(false)
  const [hidden, setHidden] = useState(false) // 下滑收起 / 上滑弹出
  const [footerInView, setFooterInView] = useState(false)
  const lastY = useRef(0)
  const ticking = useRef(false)

  /* 选项竖列对齐母按钮：展开时测量母按钮在栏内的横向位置（Skyer 2026-09-25） */
  const barRef = useRef<HTMLDivElement>(null)
  const btnRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [btnOffset, setBtnOffset] = useState(0)
  useEffect(() => {
    if (!openMenu) return
    const measure = () => {
      const btn = btnRefs.current[openMenu]
      const bar = barRef.current
      if (!btn || !bar) return
      // 竖列文字起点 = 母按钮文字起点（panel 全宽与 bar 同缘，直接取按钮视口 x）
      setBtnOffset(Math.max(0, btn.getBoundingClientRect().left - bar.getBoundingClientRect().left))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [openMenu])

  const hijackActive = useSyncExternalStore(
    subscribeHijack,
    () => getHijackRange() !== null,
  )

  /* reduced-transparency：玻璃层退纯色底（GlassSurface 的磨砂语义不适用） */
  const [reduceTransparency, setReduceTransparency] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-transparency: reduce)')
    const on = () => setReduceTransparency(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  /* 劫持区间激活时（sticky 冻结纵向滚动、scroll 事件停发）→ 强制常显 */
  useEffect(() => {
    if (hijackActive) setHidden(false)
  }, [hijackActive])

  /* ---------- 滚动行为：下滑收起、上滑弹出（信任屏劫持区间内禁用） ----------
     2026-09-25 Skyer 调整：Hero 页内（≤100vh）无论滑动速度如何都不收起；
     玻璃底也只在出 Hero 后出现（Hero 内顶栏无背景不变）。 */
  useEffect(() => {
    const onScroll = () => {
      if (ticking.current) return
      ticking.current = true
      requestAnimationFrame(() => {
        ticking.current = false
        const y = window.scrollY
        const heroEnd = window.innerHeight
        setScrolledPastHero(y > heroEnd)

        const range = getHijackRange()
        const inHijack = range !== null && y >= range.top && y <= range.bottom
        if (inHijack || y <= heroEnd) {
          setHidden(false) // 劫持区间 / Hero 页内：常显
        } else {
          // 上滑弹出更灵敏（Skyer 2026-09-25：阈值 8→3px，轻微上滑即弹出）
          const delta = y - lastY.current
          if (Math.abs(delta) > 3) setHidden(delta > 0)
        }
        lastY.current = y
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  /* ---------- 页尾进入视口 → 加深遮罩 ---------- */
  useEffect(() => {
    const footer = document.getElementById('landing-footer')
    if (!footer || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setFooterInView(e.isIntersecting), {
      threshold: 0.15,
    })
    io.observe(footer)
    return () => io.disconnect()
  }, [])

  /* ---------- Esc 关闭 + 失焦关闭 ---------- */
  useEffect(() => {
    if (!openMenu) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenMenu(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [openMenu])

  const closePanel = useCallback(() => setOpenMenu(null), [])
  const toggleMenu = useCallback((key: Exclude<MenuKey, null>) => {
    setOpenMenu((cur) => (cur === key ? null : key))
  }, [])

  const authed = status === 'authenticated'
  const panel = openMenu ? PANELS[openMenu] : null
  // 背景失焦虚化（backdrop-filter + 遮罩）与 reduced-transparency 降级均在 CSS 内处理

  return (
    <>
      {/* 背景失焦遮罩层（展开 mega 面板时） */}
      <div
        className={`${styles.scrim} ${openMenu ? styles.scrimOn : ''} ${footerInView ? styles.scrimDeep : ''}`}
        aria-hidden
        onClick={closePanel}
      />

      <header
        className={[
          styles.nav,
          hidden && !openMenu ? styles.navHidden : '',
          scrolledPastHero ? styles.navSolid : '',
          footerInView ? styles.navFooter : '',
        ].join(' ')}
        onMouseLeave={closePanel}
      >
        {/* 背景层：下拉展开时顶栏连同面板一起转纯色（2026-09-25 Skyer）；
            出 Hero 后为 GlassSurface 玻璃底（reduced-transparency → 纯色回退） */}
        {openMenu ? (
          <div className={styles.navSolidBg} aria-hidden />
        ) : scrolledPastHero &&
          (reduceTransparency ? (
            <div className={styles.navBgFallback} aria-hidden />
          ) : (
            <div className={styles.glassLayer} aria-hidden>
              <GlassSurface
                width="100%"
                height="100%"
                borderRadius={0}
                backgroundOpacity={footerInView ? 0.55 : 0.38}
                blur={14}
                saturation={1.3}
                className={styles.glassNav}
                style={{ position: 'absolute', inset: 0 }}
              />
            </div>
          ))}

        {/* 2026-09-25 Skyer：菜单移到 logo 后面（左侧成组），登录右侧；容器向两边靠 */}
        <div className={`${styles.bar} landing-wide`} ref={barRef}>
          <div className={styles.barLeft}>
            <Link to="/" className={styles.logo} aria-label="EpochX 首页" onClick={closePanel}>
              <img
                src="/brand/logo-mark-on-dark-trim.png"
                alt=""
                className={styles.logoMark}
                height={28}
              />
              <span className={styles.logoWordWrap}>
                <img
                  src="/brand/logo-wordmark-on-dark.png"
                  alt=""
                  className={styles.logoWord}
                  height={28}
                />
              </span>
            </Link>

            <nav className={styles.menus} aria-label="主导航">
              {(NAV_COPY.menus as readonly string[]).map((label) => {
                const key = label === NAV_COPY.menus[0] ? 'product'
                  : label === NAV_COPY.menus[1] ? 'pricing'
                  : 'resources'
                const isOpen = openMenu === key
                return (
                  <button
                    key={key}
                    ref={(el) => { btnRefs.current[key] = el }}
                    type="button"
                    className={`${styles.menuBtn} ${isOpen ? styles.menuBtnOn : ''}`}
                    aria-expanded={isOpen}
                    aria-haspopup="true"
                    // hover / click / focus 三种触发同效（dev-spec §4.0 可达性）
                    onMouseEnter={() => setOpenMenu(key as Exclude<MenuKey, null>)}
                    onFocus={() => setOpenMenu(key as Exclude<MenuKey, null>)}
                    onClick={() => toggleMenu(key as Exclude<MenuKey, null>)}
                  >
                    {label}
                    {key === 'pricing' && <span className={styles.naTag}>{NAV_COPY.pricingNa}</span>}
                  </button>
                )
              })}
            </nav>
          </div>

          {authed ? (
            <Link to="/study-guide" className={styles.loginBtn}>
              {NAV_COPY.enterApp}
            </Link>
          ) : (
            <Link to="/login" className={styles.loginBtn}>
              {NAV_COPY.login}
            </Link>
          )}
        </div>

        {/* mega 面板：整个顶栏下拉展开（关闭时内容不渲染，避免零高容器里的链接可聚焦）。
            2026-09-25 Skyer 重排：选项竖列对齐母按钮位置 → 竖分割线 → 放大加粗纯白 lead 分行；
            面板内容区定高（不同菜单高度一致），切换淡入。 */}
        <div className={`${styles.panel} ${openMenu && panel ? styles.panelOpen : ''}`}>
          {openMenu && panel && (
            <div key={openMenu} className={`${styles.panelInner} landing-wide`} style={{ paddingLeft: btnOffset }}>
              <ul className={styles.panelList}>
                {panel.items.map((item) => (
                  <li key={item.name}>
                    {item.href ? (
                      <Link to={item.href} className={styles.panelLink} onClick={closePanel}>
                        {item.name}
                      </Link>
                    ) : (
                      /* 占位项：未上线 / 待补——灰态，不留空 href */
                      <span className={styles.panelLinkPlaceholder}>{item.name}</span>
                    )}
                  </li>
                ))}
              </ul>
              <span className={styles.panelDivider} aria-hidden />
              <p className={styles.panelLead}>{panel.lead}</p>
            </div>
          )}
        </div>
      </header>
    </>
  )
}

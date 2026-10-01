/**
 * Docs · 公开文档站页面外壳
 *
 * 视觉定位：visual-language §8「产品内基础层」+ §8.4「文档页视觉定档」。
 * 文档页是产品重构以来第一个真正落地的新视觉页面，将来 X1 重做产品内页面时
 * **它会被当作样板间参照**——所以这一页写得比一般页面规矩。
 *
 * 几条不做的事（都是 §8/§4 的明令，不是个人偏好）：
 * - 不用液态玻璃（§8.1 第 5 条：旧语言不再使用）
 * - 不用大光场 / WebGL / 粒子（§4：强度由「这个区域要不要读字」决定，这里有正文）
 * - 蓝色只出现在「当前项 / 焦点」上（§4：蓝色出口只有三个 token）
 * - 不套 AppShell、不套 RequireAuth：公开文档，不该要登录，也不是产品导航的一部分
 * - 不用 LaunchScreen / CustomCursor：旧液态玻璃语言，会干扰阅读（与落地页同款处理）
 *
 * 结构（2026-09-29 Skyer：加顶栏）：shell 纵向两段——DocsTopbar（sticky）+
 * bodyRow（侧栏 + 正文）。顶栏带 logo 全称（→ 官网）、「索引」钮（→ /docs）、
 * 站内搜索、日夜主题切换；文章页标题行最右侧是复制按钮（DocsCopyMenu）。
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import DocsSidebar from '../../components/Docs/DocsSidebar/DocsSidebar'
import DocsProse from '../../components/Docs/DocsProse/DocsProse'
import DocsToc from '../../components/Docs/DocsToc/DocsToc'
import DocsPager from '../../components/Docs/DocsPager/DocsPager'
import DocsCard from '../../components/Docs/DocsCard/DocsCard'
import DocsTopbar from '../../components/Docs/DocsTopbar/DocsTopbar'
import DocsCopyMenu from '../../components/Docs/DocsCopyMenu/DocsCopyMenu'
import {
  extractHeadings,
  getNeighbours,
  getPage,
  getSections,
  DOC_INDEX_PATH,
} from './registry'
import styles from './Docs.module.css'

/**
 * 内部路由：/docs 索引 + /docs/:section/:slug。
 * App.jsx 挂的是 `/docs/*`（一整棵子树），细分在这里收口。
 */
export default function DocsRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DocsIndex />} />
      <Route path=":section/:slug" element={<DocArticle />} />
      <Route path="*" element={<Navigate to={DOC_INDEX_PATH} replace />} />
    </Routes>
  )
}

/** 入口页（/docs 本身） */
export function DocsIndex() {
  const sections = getSections()
  useEffect(() => {
    document.title = 'EpochX 文档'
  }, [])
  return (
    <div className={styles.shell}>
      <DocsTopbar />
      <div className={styles.bodyRow}>
        <DocsSidebar sections={sections} />
        <main className={styles.main}>
          <div className={styles.column}>
            <header className={styles.pageHead}>
              <h1 className={styles.pageTitle}>文档</h1>
              <p className={styles.lede}>
                EpochX 的使用说明。现在能用的功能在这里；还在做的会在目录里标出来。
              </p>
            </header>
            {sections.map((section) => (
              <section key={section.key} className={styles.indexSection}>
                <h2 className={styles.indexSectionTitle}>{section.label}</h2>
                <ul className={styles.indexList}>
                  {section.pages.map((page) => (
                    <li key={page.path}>
                      <Link className={styles.indexItem} to={page.path}>
                        <span className={styles.indexItemTitle}>{page.title}</span>
                        {page.status === 'building' && (
                          <span className={styles.tagBuilding}>开发中</span>
                        )}
                        {page.status === 'placeholder' && (
                          <span className={styles.tagPlaceholder}>待定</span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </main>
      </div>
    </div>
  )
}

/** 文章页（/docs/:section/:slug） */
export function DocArticle() {
  const { section = '', slug = '' } = useParams()
  const page = getPage(section, slug)
  const [menuOpen, setMenuOpen] = useState(false)
  const [activeHeadingId, setActiveHeadingId] = useState<string | null>(null)

  useEffect(() => {
    setMenuOpen(false)
    // 换页回到顶部，否则从长文底部跳到下一篇会停在半空
    window.scrollTo(0, 0)
  }, [section, slug])

  // 标签页标题随页走：index.html 的 <title> 写死「EpochX」，38 篇共用一个标题
  useEffect(() => {
    document.title = page ? `${page.title} · EpochX 文档` : '页面不存在 · EpochX 文档'
  }, [page])

  // 抽屉开着时锁住背后滚动，避免两层滚动叠在一起
  useEffect(() => {
    if (!menuOpen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
    }
  }, [menuOpen])

  // hook 必须全部在 `if (!page)` 早退之前调用：同一组件实例在正常页与 404
  // 之间切换时（如历史记录前进/后退），早退分支少了 useMemo 会让 hook 数量
  // 变化，React 直接抛错白屏
  const headings = useMemo(() => (page ? extractHeadings(page.body) : []), [page])
  const sections = getSections()
  const { prev, next } = page
    ? getNeighbours(page)
    : { prev: undefined, next: undefined }

  // 「本页」目录滚动跟随（scroll-spy）：视口 96px 处作阅读线，
  // 最后一个越过它的标题即当前小节。96 = 顶栏 56 + 余量 40，必须大于
  // 锚点落点（scroll-margin-top 56+16=72），否则点目录跳转后那一节不会亮。
  // 不做 rAF 节流：11 个标题的 getBoundingClientRect 开销可忽略，且
  // rAF 在冻结的合成器环境会饿死（落地页已踩过一次），scroll 回调直呼最稳
  useEffect(() => {
    if (!page) {
      setActiveHeadingId(null)
      return
    }
    const ids = headings.map((h) => h.id)
    if (ids.length === 0) {
      setActiveHeadingId(null)
      return
    }
    const READING_LINE = 96
    const update = () => {
      let current: string | null = null
      for (const id of ids) {
        const el = document.getElementById(id)
        if (!el) continue
        if (el.getBoundingClientRect().top <= READING_LINE) current = id
        else break
      }
      setActiveHeadingId(current)
    }
    update()
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [page, headings])

  if (!page) return <DocNotFound />

  return (
    <div className={styles.shell}>
      <DocsTopbar />
      <div className={styles.bodyRow}>
        <button
          type="button"
          className={`${styles.menuButton}${menuOpen ? ' ' + styles.menuButtonHidden : ''}`}
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-label="目录"
        >
          目录
        </button>
        {menuOpen && (
          <button
            type="button"
            className={styles.scrim}
            aria-label="关闭目录"
            onClick={() => setMenuOpen(false)}
          />
        )}
        <DocsSidebar
          sections={sections}
          currentPath={page.path}
          open={menuOpen}
          onNavigate={() => setMenuOpen(false)}
        />
        <main className={styles.main}>
          <div className={styles.contentRow}>
            <div className={styles.column}>
              <DocsProse
                body={page.body}
                page={page}
                actions={<DocsCopyMenu markdown={page.body} pageTitle={page.title} />}
              />
              <DocsPager prev={prev} next={next} />
              <p className={styles.pilotNote}>
                学生团队开发，pilot 封测，不代表最终产品形态和品质。
              </p>
            </div>
            <DocsToc items={headings} activeId={activeHeadingId} />
          </div>
        </main>
      </div>
    </div>
  )
}

function DocNotFound() {
  const navigate = useNavigate()
  return (
    <div className={styles.shell}>
      <DocsTopbar />
      <div className={styles.bodyRow}>
        <main className={styles.main}>
          <div className={styles.column}>
            <DocsCard title="这一页不存在">
              <p>链接可能过期了，或者页面改名了。</p>
              <p>
                <button type="button" className={styles.backBtn} onClick={() => navigate(DOC_INDEX_PATH)}>
                  回到文档目录
                </button>
              </p>
            </DocsCard>
          </div>
        </main>
      </div>
    </div>
  )
}

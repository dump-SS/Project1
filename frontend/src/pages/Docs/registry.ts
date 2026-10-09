/**
 * 文档站内容登记表（docs-site-structure §12）
 *
 * 做法：Vite 的 `import.meta.glob` 在打包期把 content 目录下全部 md（按两层子目录）
 * 全量读进来，运行期不需要 fs、不需要后端、不需要索引服务。
 * 新增页面只需在 content/ 下建 md 文件，本表自动收录（§13 维护规则第 1 条）。
 *
 * 排序：走 frontmatter `order`，**不用文件名编号**——中间插新页只改 order，
 * 不用全量重命名。建议用 10/20/30 的间隔值。
 *
 * 路由：/docs（索引）+ /docs/:section/:slug，section/slug 取自文件路径。
 * 因此文件名与章名必须用 ASCII，中文名在 URL 里要百分号编码。
 */
import { useMemo } from 'react'

export type DocStatus = 'implemented' | 'building' | 'placeholder'

export interface DocPage {
  /** 文件名（不含扩展名），= URL 里的 slug */
  slug: string
  /** 目录名，= URL 里的 section */
  section: string
  title: string
  /** frontmatter section 字段的中文章名，用于分组显示 */
  sectionLabel: string
  order: number
  status: DocStatus
  updated: string
  /** 去掉 frontmatter 后的正文 markdown */
  body: string
  /** /docs/:section/:slug */
  path: string
}

export interface DocSection {
  /** 目录名 = URL segment */
  key: string
  label: string
  pages: DocPage[]
}

const FILES = import.meta.glob('./content/**/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** 章的中文名 → 目录名。两侧必须与 content/ 下的目录名一致。 */
const SECTION_LABELS: Record<string, string> = {
  'getting-started': '开始使用',
  features: '功能说明',
  privacy: '隐私与安全',
  account: '账户与设置',
  billing: '价格与计费',
  faq: '常见问题',
  reference: '参考',
}

/** 章的展示顺序。目录按这个顺序排，不按目录名排。 */
const SECTION_ORDER = [
  'getting-started',
  'features',
  'privacy',
  'account',
  'billing',
  'faq',
  'reference',
]

/**
 * 极简 frontmatter 解析：只吃 `key: value`，不引 yaml 依赖（不为一个
 * 固定形状的元数据块增加包体积）。
 */
function parseFrontmatter(raw: string): { fields: Record<string, string>; body: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw)
  if (!m) return { fields: {}, body: raw }
  const fields: Record<string, string> = {}
  for (const line of m[1].split(/\r?\n/)) {
    const i = line.indexOf(':')
    if (i < 1) continue
    fields[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return { fields, body: raw.slice(m[0].length) }
}

function buildPages(): DocPage[] {
  const pages: DocPage[] = []
  for (const [file, raw] of Object.entries(FILES)) {
    // ./content/<section>/<slug>.md
    const m = /^\.\/content\/([^/]+)\/([^/]+)\.md$/.exec(file)
    if (!m) continue
    const [, section, slug] = m
    const { fields, body } = parseFrontmatter(raw)
    const status = fields.status
    if (status !== 'implemented' && status !== 'building' && status !== 'placeholder') {
      // 状态不合法时不静默吞掉——build 期就会暴露
      console.warn(`[docs] ${file} 的 status 非法：${JSON.stringify(status)}`)
    }
    pages.push({
      slug,
      section,
      title: fields.title ?? slug,
      sectionLabel: fields.section ?? SECTION_LABELS[section] ?? section,
      order: Number(fields.order ?? 999),
      status: (status as DocStatus) ?? 'placeholder',
      updated: fields.updated ?? '',
      body,
      path: `/docs/${section}/${slug}`,
    })
  }
  pages.sort((a, b) =>
    SECTION_ORDER.indexOf(a.section) - SECTION_ORDER.indexOf(b.section) || a.order - b.order,
  )
  return pages
}

const ALL_PAGES = buildPages()

const BY_PATH = new Map(ALL_PAGES.map((p) => [p.path, p]))

const SECTIONS: DocSection[] = SECTION_ORDER.map((key) => ({
  key,
  label: SECTION_LABELS[key] ?? key,
  pages: ALL_PAGES.filter((p) => p.section === key),
})).filter((s) => s.pages.length > 0)

export const DOC_INDEX_PATH = '/docs'

export function getSections(): DocSection[] {
  return SECTIONS
}

export function getAllPages(): DocPage[] {
  return ALL_PAGES
}

/** 按路径取页；取不到返回 undefined（由调用方走 404）。 */
export function getPage(section: string, slug: string): DocPage | undefined {
  return BY_PATH.get(`/docs/${section}/${slug}`)
}

/** 索引页要展示的入口页：每章 order 最小的那一页。 */
export function getSectionEntryPages(): DocPage[] {
  return SECTIONS.map((s) => s.pages[0]).filter(Boolean)
}

/** 上一篇 / 下一篇：按全文顺序（跨章连续），用于页脚导航。 */
export function getNeighbours(current: DocPage): { prev?: DocPage; next?: DocPage } {
  const i = ALL_PAGES.findIndex((p) => p.path === current.path)
  if (i < 0) return {}
  return { prev: ALL_PAGES[i - 1], next: ALL_PAGES[i + 1] }
}

/** 同章的页，用于右侧目录或「本章其他页」。 */
export function getSectionSiblings(current: DocPage): DocPage[] {
  return SECTIONS.find((s) => s.key === current.section)?.pages ?? []
}

/* ================= 站内搜索（2026-09-29 Skyer：顶栏加搜索）=================
 * 纯客户端（§14 待定项 4 的「客户端匹配」方案）：对 ALL_PAGES 的
 * 标题 + 正文做子串匹配，不引依赖、不上索引服务。38 篇量级即时出结果。
 */

/** 把查询拆成词：空白分隔，AND 语义（每个词都要命中）。 */
export function splitQueryTerms(query: string): string[] {
  return query.trim().split(/\s+/).filter(Boolean)
}

/** 正文 → 参与搜索/摘要的纯文本（剥掉 markdown 记号——摘要里不能露出 ** ## []() ）。 */
const PLAIN_CACHE = new Map<string, string>()
function plainBody(page: DocPage): string {
  let plain = PLAIN_CACHE.get(page.path)
  if (plain === undefined) {
    plain = page.body
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/`{1,3}([^`]*)`{1,3}/g, '$1')
      .replace(/\*\*([^*]*)\*\*/g, '$1')
      .replace(/^\s*#{1,6}\s+/gm, '')
      .replace(/^\s*[-*+]\s+/gm, '')
      .replace(/^\s*>\s?/gm, '')
      .replace(/^\s*-{3,}\s*$/gm, ' ')
      .replace(/\|/g, ' ')
    PLAIN_CACHE.set(page.path, plain)
  }
  return plain
}

export interface DocSearchHit {
  page: DocPage
  /** 命中位置：标题命中排前面展示、无摘要；正文命中带上下文片段 */
  where: 'title' | 'body'
  /** 正文命中时的上下文片段（命中词前后各 ~30 字，已压平空白） */
  snippet?: string
}

/** 子串搜索。结果按全站顺序（章 → order）返回，最多 limit 条。 */
export function searchPages(query: string, limit = 8): DocSearchHit[] {
  const terms = splitQueryTerms(query).map((t) => t.toLowerCase())
  if (terms.length === 0) return []
  const hits: DocSearchHit[] = []
  for (const page of ALL_PAGES) {
    // 摘要与正文匹配都走剥过记号的纯文本；内容是中文 + ASCII，
    // toLowerCase 不改变长度，索引可安全映射回原文
    const title = page.title.toLowerCase()
    const body = plainBody(page).toLowerCase()
    let inTitle = false
    let inBody = false
    for (const term of terms) {
      const t = title.includes(term)
      const b = body.includes(term)
      if (!t && !b) {
        inTitle = false
        inBody = false
        break
      }
      inTitle = inTitle || t
      inBody = inBody || b
    }
    if (!inTitle && !inBody) continue
    let snippet: string | undefined
    if (inBody) {
      const term = terms.find((t) => body.includes(t))
      if (term) {
        const plain = plainBody(page)
        const i = body.indexOf(term)
        const start = Math.max(0, i - 30)
        const end = Math.min(plain.length, i + term.length + 30)
        snippet =
          (start > 0 ? '…' : '') +
          plain.slice(start, end).replace(/\s+/g, ' ') +
          (end < plain.length ? '…' : '')
      }
    }
    hits.push({ page, where: inTitle ? 'title' : 'body', snippet })
    if (hits.length >= limit) break
  }
  return hits
}

/**
 * 从 markdown 正文里抽出 h2/h3 标题，做右侧目录。
 * 标题文本里的行内标记（`**`、`` ` ``）在渲染时会被去掉，这里同步剥掉。
 */
export function extractHeadings(body: string): { id: string; text: string; level: 2 | 3 }[] {
  const out: { id: string; text: string; level: 2 | 3 }[] = []
  for (const line of body.split(/\r?\n/)) {
    const m = /^(#{2,3})\s+(.+?)\s*$/.exec(line)
    if (!m) continue
    const text = m[2]
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .trim()
    out.push({ id: headingId(text), text, level: m[1].length === 2 ? 2 : 3 })
  }
  return out
}

/** 标题 → DOM id。中文直接用原文（现代浏览器与 URL 都能处理）。 */
export function headingId(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\w\u4e00-\u9fa5-]/g, '')
}

/** `useMemo` 包一层，供组件里安全使用（当前是模块级常量，包一层只为调用方语义清晰）。 */
export function useDocs() {
  return useMemo(() => ({ sections: getSections(), all: getAllPages() }), [])
}

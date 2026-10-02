/**
 * DocsProse · 长文排版（visual-language §8.4.2）
 *
 * 组件化的理由（§8.4.6）：markdown 正文这套排版是文档页做出来的第一件可复用东西。
 * 产品里的「产品说的话」「设置说明」「错误解释」将来都是同一套排版。
 *
 * 度量值全部取自 §8.4.1 / §8.4.2，**不另取一套**：
 * - 行宽 ≈ 700–760px（中文 40–45 字/行）→ --docs-measure
 * - 正文 15 / 小字 13 / H1 28 / H2 20 / H3 16
 * - 行高 长文 1.8 / 列表说明 1.6 / 标题 1.3
 * - 段落间距 16px，章节间距 24–32px
 * - 字体按时态（§5）：标题无衬线（正在发生）、正文衬线（已写下来的）
 * - 代码块：等宽 + hairline + 极淡底，**不染色**、不做深色反白以外的装饰
 */
import { useMemo } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { headingId, type DocPage } from '../../../pages/Docs/registry'
import styles from './DocsProse.module.css'

export interface DocsProseProps {
  body: string
  /** 传入则渲染页头（H1 + 更新时间 + 状态标识） */
  page?: DocPage
  /** 页头标题行最右侧的操作区（2026-09-30 Skyer：复制按钮放标题同行最右） */
  actions?: ReactNode
}

export default function DocsProse({ body, page, actions }: DocsProseProps) {
  const components = useMemo<Components>(
    () => ({
      // 标题自动挂 id，右侧目录靠它跳转
      h1: ({ children }) => <h1 id={headingId(textOf(children))}>{children}</h1>,
      h2: ({ children }) => <h2 id={headingId(textOf(children))}>{children}</h2>,
      h3: ({ children }) => <h3 id={headingId(textOf(children))}>{children}</h3>,
      // 外链一律新窗口打开并断开 opener；站内 /docs 链接与同页锚点交给浏览器处理
      a: ({ href, children }) => {
        // 同页锚点（# 开头）必须走内部分支：否则会被当外链在新标签打开，点了跳空
        const isInternal = !href || href.startsWith('/') || href.startsWith('#')
        if (isInternal) return <a href={href}>{children}</a>
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        )
      },
      // 表格横向滚动，不撑破行宽
      table: ({ children }) => (
        <div className={styles.tableScroll}>
          <table>{children}</table>
        </div>
      ),
    }),
    [],
  )

  return (
    <article className={styles.prose}>
      {page && <PageHeader page={page} actions={actions} />}
      {/* GFM：表格 / 删除线 / 任务列表。docs 内容页大量使用表格，缺了它表格会渲染成原始管道文本 */}
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{body}</ReactMarkdown>
    </article>
  )
}

function PageHeader({ page, actions }: { page: DocPage; actions?: ReactNode }) {
  return (
    <header className={styles.pageHead}>
      <div className={styles.pageHeadRow}>
        <h1 className={styles.pageTitle}>{page.title}</h1>
        {actions && <div className={styles.pageActions}>{actions}</div>}
      </div>
      <p className={styles.pageMeta}>
        {page.status === 'building' && <span className={styles.badge}>开发中</span>}
        {page.status === 'placeholder' && <span className={styles.badge}>待定</span>}
        {page.updated && <span>最后更新 {page.updated}</span>}
      </p>
    </header>
  )
}

/** 从 react children 里取纯文本，用于生成标题 id。 */
function textOf(node: unknown): string {
  if (node == null || node === false) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (typeof node === 'object' && 'props' in (node as { props?: unknown })) {
    const props = (node as { props?: { children?: unknown } }).props
    return textOf(props?.children)
  }
  return ''
}

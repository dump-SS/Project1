/**
 * DocsSidebar · 侧栏（visual-language §8.4.4）
 *
 * 规矩照 §8.4.4，不自行发挥：
 * - 宽度 240–280px（取 --docs-sidebar-w）
 * - 当前项 = **蓝墨水左细条（2px）+ 文字转蓝**（--accent / --brand-blue）
 * - 分组标题用**衬线小字**（注释层级）
 * - hover 与 :focus-visible 等价（§9.1）——触屏与键盘不能只靠鼠标
 * - `building` 页灰标 + 「开发中」标签，`placeholder` 虚线（§4：不可用状态一律灰）
 * - 「致家长」项加浅色 chip「家长」标识（§8.4.4 / 骨架 §9）
 *
 * ⭐ 写在 components/ 而不是 Docs 页里：将来这就是产品内的侧栏。
 */
import { NavLink } from 'react-router-dom'
import type { DocSection, DocPage } from '../../../pages/Docs/registry'
import styles from './DocsSidebar.module.css'

/** 需要「家长」chip 的页（骨架 §9：浅色 chip，不加色，只加标识） */
const PARENT_CHIP = 'for-parents'

/** 开发中页的标签文案 */
const BUILDING_LABEL = '开发中'

export interface DocsSidebarProps {
  sections: DocSection[]
  currentPath?: string
  /** 移动端抽屉是否展开（由页面外壳控制） */
  open?: boolean
  onNavigate?: () => void
}

export default function DocsSidebar({
  sections,
  currentPath,
  open = false,
  onNavigate,
}: DocsSidebarProps) {
  return (
    <nav
      className={`${styles.sidebar}${open ? ' ' + styles.open : ''}`}
      aria-label="文档目录"
    >
      {sections.map((section) => (
        <div key={section.key} className={styles.group}>
          <p className={styles.groupLabel}>{section.label}</p>
          <ul className={styles.list}>
            {section.pages.map((page) => (
              <li key={page.path}>
                <NavLink
                  to={page.path}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    [
                      styles.item,
                      isActive || currentPath === page.path ? styles.current : '',
                      page.status === 'placeholder' ? styles.placeholder : '',
                      page.status === 'building' ? styles.building : '',
                    ]
                      .filter(Boolean)
                      .join(' ')
                  }
                >
                  <span className={styles.itemText}>{page.title}</span>

                  {page.slug === PARENT_CHIP && (
                    <span className={styles.chipParent}>家长</span>
                  )}

                  {/* building 也要显式标出来：「占位也要占得诚实」，
                      避免访客以为点错或内容没加载（骨架 §11） */}
                  {page.status === 'building' && (
                    <span className={styles.tagBuilding}>{BUILDING_LABEL}</span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

export type { DocPage, DocSection }

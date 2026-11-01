import { useEffect, useRef, useState } from 'react'
import { subjectColors, subjectLabels } from '@/styles/theme'
import styles from './index.module.css'

/**
 * D56 · 学科工具顶栏（F 板块 M5，壳由 X1 配合）。
 *
 * 交互链（目标态 §4.10.1，逐句照做）：
 *   任意页面悬停「页面上边界」→ 一条小黑条滑出 → 单击 → 下拉出菜单。
 *   菜单占据页面上部、左右抵边，把原页面内容「挤」到下面（下方内容无法完全显示）。
 *   首卡 = 彩色学科卡（斜置图标背景）：悬停 → 略浮动放大 + 整个界面背景模糊 +
 *   卡片下方展开全部学科；单击某学科 → 替换首卡、工具集随之切换。
 *   后续卡 = 深灰工具卡（名称 + 图标）。
 *   单击「学科卡」本身 → 顶栏收起、页面恢复，卡片扩大至页面居中成「学科工具浮窗」。
 *
 * 工具集跟随学科切换（§4.10.2）。pilot 只做科学计算器一个真工具（D57，dev-1 交付中），
 * 其余位置保留「开发中」占位——TOOL_REGISTRY 的 ready 标志就是接线点：
 * D57 合并后把 calculator 的 ready 置 true 并接上打开回调即可，本组件零改动。
 *
 * 术语注意（§4.10.1 澄清）：这里的「界面虚化」= 背景模糊（景深突出），
 * 与收藏的「虚化」（文本模糊）是两回事，CSS 用 backdrop-filter 实现。
 */

/** 每个学科的工具集。pilot：计算器（D57 未就绪 → 开发中占位）+ 通用占位一张。 */
const TOOL_REGISTRY = {
  calculator: { id: 'calculator', name: '科学计算器', ready: false },
  more: { id: 'more', name: '更多工具', ready: false },
}
const SUBJECT_TOOLS = [TOOL_REGISTRY.calculator, TOOL_REGISTRY.more]

const SUBJECT_CODES = Object.keys(subjectLabels)

export default function SubjectTools() {
  const [peek, setPeek] = useState(false) // 黑条是否滑出
  const [open, setOpen] = useState(false) // 下拉菜单是否展开
  const [subject, setSubject] = useState('SX') // 当前学科（首卡）
  const [browsing, setBrowsing] = useState(false) // 悬停学科卡：背景模糊 + 展开全部学科
  const [floatOpen, setFloatOpen] = useState(false) // 学科工具浮窗（居中）
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)

  // Esc 关闭：面板 / 浮窗 / 展开态，一次一层
  useEffect(() => {
    if (!open && !floatOpen && !browsing) return
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      if (browsing) setBrowsing(false)
      else if (floatOpen) setFloatOpen(false)
      else if (open) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, floatOpen, browsing])

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current) }, [])

  const showToast = (text) => {
    setToast(text)
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), 1600)
  }

  const openTool = (tool) => {
    if (tool.ready) {
      // D57 接线点：calculator.ready = true 后在这里打开计算器浮窗
      showToast(`${tool.name}即将可用`)
      return
    }
    showToast('该工具开发中，敬请期待')
  }

  const pickSubject = (code) => {
    setSubject(code)
    setBrowsing(false)
  }

  const openFloat = () => {
    setBrowsing(false)
    setOpen(false) // 顶栏收起、页面恢复（§4.10.1）
    setPeek(false)
    setFloatOpen(true)
  }

  const tools = SUBJECT_TOOLS

  return (
    <>
      {/* ① 上边界感应区：悬停 → 小黑条滑出（§4.10.1 触发） */}
      {!open && !floatOpen && (
        <div
          className={styles.edgeSensor}
          onMouseEnter={() => setPeek(true)}
          aria-hidden="true"
        />
      )}

      {/* ② 小黑条：滑出后单击才展开菜单（悬停不展开，避免误触） */}
      <button
        type="button"
        className={`${styles.peekStrip} ${peek && !open && !floatOpen ? styles.peekStripOn : ''}`}
        onClick={() => { setOpen(true); setPeek(false) }}
        aria-label="打开学科工具"
        aria-expanded={open}
        onMouseLeave={() => setPeek(false)}
        tabIndex={peek ? 0 : -1}
      >
        学科工具
      </button>

      {/* ③ 背景模糊层：悬停学科卡时整个界面景深突出（术语=背景模糊，非收藏的虚化） */}
      {(browsing || floatOpen) && (
        <div
          className={styles.blurLayer}
          onClick={() => { setBrowsing(false); setFloatOpen(false) }}
          aria-hidden="true"
        />
      )}

      {/* ④ 下拉菜单：占据页面上部、左右抵边，下方内容被「挤」得显示不全 */}
      <section
        className={`${styles.panel} ${open ? styles.panelOn : ''}`}
        aria-label="学科工具"
        aria-hidden={!open}
      >
        <div className={styles.row}>
          {/* 首卡：彩色学科卡（背景=该学科斜置图标） */}
          <button
            type="button"
            className={styles.subjectCard}
            style={{ background: subjectColors[subject] }}
            onMouseEnter={() => setBrowsing(true)}
            onFocus={() => setBrowsing(true)}
            onClick={openFloat}
            title={`${subjectLabels[subject]} · 单击打开学科工具浮窗`}
          >
            <span className={styles.subjectGlyph} aria-hidden="true">
              {subjectLabels[subject].slice(0, 1)}
            </span>
            <span className={styles.subjectName}>{subjectLabels[subject]}</span>
            <span className={styles.subjectHint}>学科工具</span>
          </button>

          {/* 后续卡：深灰工具卡（宽度略大于学科卡） */}
          {tools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              className={styles.toolCard}
              onClick={() => openTool(tool)}
              title={tool.ready ? tool.name : `${tool.name} · 开发中`}
            >
              <span className={styles.toolIcon} aria-hidden="true">
                {tool.id === 'calculator' ? '＝' : '⋯'}
              </span>
              <span className={styles.toolName}>{tool.name}</span>
              {!tool.ready && <span className={styles.toolBadge}>开发中</span>}
            </button>
          ))}
        </div>

        {/* 悬停学科卡 → 下方展开全部学科（§4.10.1） */}
        <div className={`${styles.subjects} ${browsing ? styles.subjectsOn : ''}`} aria-hidden={!browsing}>
          {SUBJECT_CODES.map((code) => (
            <button
              key={code}
              type="button"
              className={`${styles.subjectChip} ${code === subject ? styles.subjectChipOn : ''}`}
              style={{ background: subjectColors[code] }}
              onClick={() => pickSubject(code)}
              tabIndex={browsing ? 0 : -1}
            >
              {subjectLabels[code]}
            </button>
          ))}
        </div>

        <p className={styles.panelHint}>提示：单击学科卡可打开居中的学科工具浮窗 · Esc 收起</p>
      </section>

      {/* ⑤ 学科工具浮窗：学科卡扩大至页面居中（§4.10.1 单击学科卡本身） */}
      {floatOpen && (
        <div className={styles.floatWrap} role="dialog" aria-label={`${subjectLabels[subject]}工具`}>
          <div className={styles.floatCard}>
            <header className={styles.floatHeader} style={{ background: subjectColors[subject] }}>
              <span className={styles.floatTitle}>{subjectLabels[subject]} · 学科工具</span>
              <button
                type="button"
                className={styles.floatClose}
                onClick={() => { setFloatOpen(false); setBrowsing(false) }}
                aria-label="关闭学科工具浮窗"
              >
                ✕
              </button>
            </header>
            <div className={styles.floatBody}>
              {tools.map((tool) => (
                <button
                  key={tool.id}
                  type="button"
                  className={styles.floatToolRow}
                  onClick={() => openTool(tool)}
                >
                  <span className={styles.toolIcon} aria-hidden="true">
                    {tool.id === 'calculator' ? '＝' : '⋯'}
                  </span>
                  <span className={styles.toolName}>{tool.name}</span>
                  {!tool.ready && <span className={styles.toolBadge}>开发中</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ⑥ 轻提示 */}
      {toast && (
        <div className={styles.toast} role="status">{toast}</div>
      )}
    </>
  )
}

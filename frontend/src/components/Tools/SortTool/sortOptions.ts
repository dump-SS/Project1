/**
 * D58 /题目排序 · 共享数据与「仅首次」光效标记（F 板块，§4.10.4）。
 *
 * 入口有两处（2026-11-01 用户拍板，替代原「独立 + 按钮」方案）：
 * ① 拍题栏的「题目排序」按钮（SortMenuButton）；② 快捷引用面板的「题目排序」Tab。
 * 两处共用这份选项数据与发送回调，都由 Chat 页接线（组件不各自 fetch）。
 */

export interface SortOption {
  kind: 'difficulty' | 'mastery' | 'custom' | 'value'
  label: string
  desc: string
  /** 难易/掌握度/价值遴选：组好的 prompt，点选即随图发送 */
  prompt?: string
  /** 自定义：模板进输入框由用户续写 */
  template?: string
}

/** 四子选项顺序 = §4.10.4 第 884-889 行表格顺序 */
export const SORT_OPTIONS: SortOption[] = [
  {
    kind: 'difficulty',
    label: '难易排序',
    desc: '按题目难度从易到难',
    prompt:
      '请对我拍的这一页题目按难度从易到难排序（一页里有多道题时给出逐题顺序），每题用一句话说明难度判断依据。',
  },
  {
    kind: 'mastery',
    label: '知识点掌握度排序',
    desc: '结合我的掌握度，差的排前面',
    prompt:
      '请结合我的知识点掌握度，对我拍的这一页题目排序：我掌握得差的排前面，逐题列出涉及的知识点和我的掌握情况。',
  },
  {
    kind: 'custom',
    label: '自定义排序',
    desc: '自己输入排序提示词',
    template: '请对我拍的这一页题目按以下要求排序：',
  },
  {
    kind: 'value',
    label: '价值遴选',
    desc: '知识点/解法交叉度高者优先',
    prompt:
      '请分析我拍的这一页里每道题涉及的知识点，指出哪些题的知识点/解法交叉度高，按刷题价值从高到低排序，并逐题说明价值理由。',
  },
]

/** 首次拍照光效「仅首次」的持久化 key（§4.10.4 第 881 行） */
export const SORT_GLOW_DONE_KEY = 'epochx:sort-glow-done'

export function hasSortGlowDone(): boolean {
  try {
    return localStorage.getItem(SORT_GLOW_DONE_KEY) === '1'
  } catch {
    return false
  }
}

/** 用户响应过引导（点开菜单 / 选中任一选项）→ 灯灭且不再出现 */
export function markSortGlowDone(): void {
  try {
    localStorage.setItem(SORT_GLOW_DONE_KEY, '1')
  } catch {
    // 隐私模式等写入失败：每会话重新引导一次，可接受
  }
}

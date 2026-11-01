/**
 * 工具 → 主对话 的跨页引用递送总线（D57，F 板块）。
 *
 * 背景：学科工具（科学计算器）挂在 AppShell 层、任意页面可开；而 Chat 页的
 * 引用块（RefChip[]）是 Chat 页自己的 state。「添加到对话」要同时完成
 * 切页（navigate('/chat')）与递引用，两者属于不同组件树。
 *
 * 方案：极简「待取信箱」——生产者写入 + 广播事件；消费者（Chat 页）
 * 挂载时取一次 + 监听事件再取（覆盖「已在 /chat」与「刚切过来」两种时序）。
 * 取即清空，不残留。
 *
 * 放在 hooks/（中性共享目录）而不是 Chat/ 或 Tools/，避免 B↔F 互相伸手
 * 进对方目录（InputArea 的 render-prop 注释确立的依赖方向约定）。
 */

export interface ToolRefPayload {
  /** 引用块展示标签，如「科学计算器」 */
  label: string
  /** 注入正文（计算器 = 全部计算输入与输出的文本） */
  text: string
  /** 来源标记（RefChip.source 协议字段），如 'f_calculator' */
  source: string
}

const EVENT = 'epochx:tool-ref-pending'

let pending: ToolRefPayload | null = null

/** 生产者：写入待递引用并广播（写新的会覆盖旧的——同一时刻只有一次「添加到对话」） */
export function setPendingToolRef(payload: ToolRefPayload): void {
  pending = payload
  window.dispatchEvent(new CustomEvent(EVENT))
}

/** 消费者：取走（并清空）当前待递引用；无则 null */
export function takePendingToolRef(): ToolRefPayload | null {
  const value = pending
  pending = null
  return value
}

/** 事件名，消费者 addEventListener 用 */
export const TOOL_REF_EVENT = EVENT

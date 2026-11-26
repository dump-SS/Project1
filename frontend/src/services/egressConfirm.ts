/**
 * 带图出域的一次性确认（A1，2026-11-27 Skyer 复核）。
 *
 * 后端在 `knowledgeAiEgressEnabled` 关闭时，对带图入口返回
 * **428 `EGRESS_CONFIRM_REQUIRED`**；`http.ts` 捕获后调用
 * `requestEgressConfirm()`，由全局 `<EgressConfirmDialog />` 弹窗，
 * 用户选择后 `resolveEgressConfirm()` 把结果交回去，再带
 * `X-Egress-Confirm: 1` 重试一次。
 *
 * 为什么用「事件 + Promise」而不是把弹窗塞进 http.ts：
 * http.ts 是 X1 独占的鉴权/错误处理层，不该依赖 React；组件层监听事件即可。
 *
 * 为什么不用 localStorage 记「不再问」：
 * 那会让「设置里关掉开关」之后弹窗仍被本地状态藏住——关了等于没关。
 * 持久授权只能由后端 `knowledgeAiEgressEnabled` 表达。
 */

export const EGRESS_CONFIRM_EVENT = 'epochx:egress-confirm'
export const EGRESS_CONFIRM_REQUIRED = 'EGRESS_CONFIRM_REQUIRED'

let resolver: ((ok: boolean) => void) | null = null

/** 等用户在弹窗里做选择。同一时刻只允许一个（后端请求是串行触发的）。 */
export function requestEgressConfirm(): Promise<boolean> {
  return new Promise((resolve) => {
    resolver = resolve
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(EGRESS_CONFIRM_EVENT))
    }
  })
}

/** 弹窗选择结果：true = 本次继续，false = 取消。 */
export function resolveEgressConfirm(ok: boolean): void {
  const pending = resolver
  resolver = null
  pending?.(ok)
}

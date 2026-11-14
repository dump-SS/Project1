/**
 * 为 .jsx 模块提供类型声明（tsconfig 只 include ts/tsx，
 * tsx 页面 import jsx 模块时需要显式声明，否则 strict 模式报 TS7016）。
 */

declare module '*/context/ThemeContext.jsx' {
  export type ThemeMode = 'day' | 'night'
  export function useTheme(): {
    theme: ThemeMode
    toggleTheme: () => void
    setTheme: (mode: ThemeMode) => void
  }
}

/** 消息级报错按钮（G 板块可复用组件，L175 挂进 Chat AI 气泡）。 */
declare module '*/components/ErrorReportButton' {
  import type { ComponentType } from 'react'
  export interface ErrorReportButtonProps {
    messageId?: string
    intent?: string
    context?: Record<string, unknown>
    label?: string
  }
  const ErrorReportButton: ComponentType<ErrorReportButtonProps>
  export default ErrorReportButton
}

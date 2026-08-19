/**
 * 为 .jsx 模块提供类型声明（tsconfig 只 include ts/tsx，
 * tsx 页面 import jsx 模块时需要显式声明，否则 strict 模式报 TS7016）。
 */

declare module '*/context/ThemeContext.jsx' {
  export type ThemeMode = 'day' | 'night'
  export function useTheme(): {
    theme: ThemeMode
    toggleTheme: () => void
  }
}

/**
 * AuthContext.jsx 的最小类型声明（落地页 TS 引用 JS 模块用；
 * tsconfig 不含 allowJs，跨语言引用需要本地声明）。
 * 与 src/context/AuthContext.jsx 的真实导出保持一致。
 */
declare module '@/context/AuthContext' {
  export type AuthStatus = 'checking' | 'authenticated' | 'anonymous'
  export interface AuthContextValue {
    status: AuthStatus
    user: { email: string } | null
    refresh: () => Promise<void>
    logout: () => Promise<void>
  }
  export function useAuth(): AuthContextValue
}

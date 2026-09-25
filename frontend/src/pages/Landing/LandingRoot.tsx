import type { ReactNode } from 'react'

/**
 * 落地页根容器。
 * - .landing 作用域承载全部页面级 token（landing.css），不污染全站；
 * - fixed 不透明背景层遮盖 body 的天空渐变底（main.jsx 全局样式），
 *   顶栏 backdrop-filter 虚化才不会透出旧主题。
 */
export default function LandingRoot({ children }: { children: ReactNode }) {
  return (
    <div className="landing">
      {/* 遮底：z 低于内容，顶栏 mega 面板的虚化对象是它而不是旧主题天空 */}
      <div
        aria-hidden
        style={{
          position: 'fixed',
          inset: 0,
          background: 'var(--lp-bg)',
          zIndex: -1,
        }}
      />
      {children}
    </div>
  )
}

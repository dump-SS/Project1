/**
 * EpochX 官网落地页（路由 `/`，不套 AppShell / RequireAuth）。
 * 视觉与文案真源：docs/visual-language.md；实施规格：docs/landing-page-dev-spec.md。
 *
 * 结构：顶栏 + 八屏（Hero / 三时代 / 功能屏×3 / 信任屏 / 图标海 / CTA+页尾）。
 * 本文件只做组装；各屏实现在 components/ 下，文案全部来自 content/。
 */
import LandingRoot from './LandingRoot'
// 页面级样式唯一入口（Tailwind utilities-only + .landing 作用域 token）。
// 非 CSS Module（工具类需全局可用），但所有规则都收在 .landing 作用域内，不泄漏全站。
import './landing.css'

export default function LandingPage() {
  return (
    <LandingRoot>
      <main id="landing-main">
        {/* 各屏组件按阶段 5 逐个接入 */}
        <p className="landing-wrap" style={{ paddingBlock: 80 }}>
          Landing under construction.
        </p>
      </main>
    </LandingRoot>
  )
}

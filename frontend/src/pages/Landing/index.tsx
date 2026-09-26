/**
 * EpochX 官网落地页（路由 `/`，不套 AppShell / RequireAuth）。
 * 视觉与文案真源：docs/visual-language.md；实施规格：docs/landing-page-dev-spec.md。
 *
 * 结构：顶栏 + 八屏（Hero / 三时代 / 功能屏×3 / 信任屏 / 图标海 / CTA+页尾）。
 * 本文件只做组装；各屏实现在 components/ 下，文案全部来自 content/。
 */
import LandingRoot from './LandingRoot'
import LandingNav from './components/LandingNav/LandingNav'
import Hero from './components/Hero/Hero'
import EpochsWindow from './components/EpochsWindow/EpochsWindow'
import ThreadsZone from './components/ThreadsZone'
import FeatureSection from './components/FeatureSection/FeatureSection'
import TrustWall from './components/TrustWall/TrustWall'
import IconSea from './components/IconSea/IconSea'
import CtaFooter from './components/CtaFooter/CtaFooter'
import { LandingLocaleProvider } from './content/i18n'
// 页面级样式唯一入口（Tailwind utilities-only + .landing 作用域 token）。
// 非 CSS Module（工具类需全局可用），但所有规则都收在 .landing 作用域内，不泄漏全站。
import './landing.css'

export default function LandingPage() {
  return (
    <LandingLocaleProvider>
      <LandingRoot>
        <LandingNav />
        <main id="landing-main">
          <Hero />
          <EpochsWindow />
          {/* 功能屏 ×3（叙事部分）：Threads 光线常驻背景（Skyer 2026-09-25）；
              顺序 = 由近及远（当下 → 事后 → 周期） */}
          <ThreadsZone>
            <FeatureSection screenId="state" />
            <FeatureSection screenId="error-book" />
            <FeatureSection screenId="review" />
          </ThreadsZone>
          <TrustWall />
          <IconSea />
          <CtaFooter />
        </main>
      </LandingRoot>
    </LandingLocaleProvider>
  )
}

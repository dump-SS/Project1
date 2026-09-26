/**
 * 落地页文案的**类型契约 + 双语入口**。
 *
 * 结构（2026-09-27 英文版接入）：
 *   copy.zh.ts / copy.en.ts —— 两套同形文案，各自独立可 review；
 *   本文件只放 interface 与 re-export，不放文案。
 *
 * ⚠️ 用显式 interface 而不是 `typeof COPY_ZH`：中文那套带 `as const` 字面量类型，
 * 直接拿来做英文的类型会因字面量不同而报错；显式 interface 还能保证**两套 key 完全对齐**
 * （漏翻一条即编译不过，这正是翻译任务最需要的保护）。
 *
 * ⚠️ 组件里不许再写死中文标点/字（如按「，」拆行）——凡与语言相关的拆分点都在文案里
 * 显式给出（例如 epochs.headlineLines 直接给两行，不再靠 indexOf('，')）。
 */

/** 支持的语言 */
export type Locale = 'zh' | 'en'

/** Hero slogan：打字机 + 退格换词编排所需的全部片段 */
export interface SloganCopy {
  /** 打字机的公共前缀（退格退到这里为止、成稿也以它开头） */
  base: string
  /** 初稿（完整打出） */
  initial: string
  /** 成稿（含句末标点） */
  final: string
  /** 新加段（加粗呈现，不含句末标点） */
  strong: string
  /** 成稿中需高亮的片段（中文「你」/ 英文 you），同时为蓝字 */
  highlight: string
}

export interface HeroActionsCopy {
  inputPlaceholder: string
  primary: string
  desktop: string
}

export interface EpochsCopy {
  headline: string
  /** 标题两行断法（显式给出，避免按中文逗号拆行） */
  headlineLines: readonly [string, string]
  sub: string
  highlight: string
}

export interface FeatureScreenCopy {
  id: string
  featureName: string
  /** 标题 = 该屏对话里产品说过的原句（含引号） */
  title: string
  /** 标题断行（可选；第一屏两行） */
  titleLines?: readonly string[]
  description: string
  dialogueId: 'S2' | 'S3' | 'S4'
}

export interface TrustCardCopy {
  id: string
  name: string
  icon: 'lock' | 'bars' | 'return' | 'shield'
  brief: string
  detail: string
  placeholder: boolean
}

export interface TrustCopy {
  title: string
  sub: string
  /** 未接入真截图的卡内占位文案（原为组件内硬编码中文） */
  placeholderLabel: string
  cards: readonly TrustCardCopy[]
}

export interface IconSeaCopy {
  caption: string
  highlight: string
  /** 顺序 = 学生的一天 */
  order: readonly string[]
}

export interface CtaCopy {
  before: string
  after: string
}

export interface FooterCopy {
  tagline: string
  links: readonly string[]
  backToTop: string
  copyrightPrefix: string
  copyrightHolder: string
  copyrightYear: string
  compliance: string
  icp: string
}

export interface NavCopy {
  menus: readonly [string, string, string]
  pricingNa: string
  productPanel: {
    lead: string
    items: readonly { name: string; href: string }[]
  }
  resourcesPanel: {
    lead: string
    items: readonly { name: string; href: string }[]
  }
  login: string
  enterApp: string
  /** 语言切换：两种语言名各自用自身语言书写（简体中文 / ENG） */
  lang: {
    zh: string
    en: string
    ariaLabel: string
  }
}

/** 读屏/结构化标签（不显示，但英文版也必须英文，否则读屏念中文） */
export interface A11yCopy {
  hero: string
  epochs: string
  featureName: string
  trust: string
  iconSea: string
  cta: string
  sendMessage: string
  footerLinks: string
  mainNav: string
  homeLink: string
  dialogueCard: string
  realDialogue: string
  desktopSoonTitle: string
}

/** 一套语言的完整文案 */
export interface LandingCopy {
  a11y: A11yCopy
  heroSlogan: SloganCopy
  heroActions: HeroActionsCopy
  epochs: EpochsCopy
  dialogueCaption: string
  featureScreens: readonly FeatureScreenCopy[]
  trust: TrustCopy
  iconSea: IconSeaCopy
  cta: CtaCopy
  footer: FooterCopy
  nav: NavCopy
}

export { COPY_ZH } from './copy.zh'
export { COPY_EN } from './copy.en'

/** Hero 草稿跨登录墙的 localStorage key（与语言无关，中英共用） */
export const HERO_DRAFT_KEY = 'epochx.landing.draft'

/** 语言选择的 localStorage key */
export const LANG_STORAGE_KEY = 'epochx.landing.locale'

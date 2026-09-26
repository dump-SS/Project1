import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { COPY_EN, COPY_ZH, LANG_STORAGE_KEY, type LandingCopy, type Locale } from './copy'
import { DIALOGUES_BY_LOCALE, type DialogueBundle } from './dialogues'

/**
 * 落地页轻量 i18n（2026-09-27 英文版接入）。
 *
 * 为什么不用 i18next / react-intl：`frontend/package.json` 是共享独占文件（AGENTS.md 铁律 3），
 * 不为一次落地页双语加依赖；落地页文案本来就集中在一处，上下文 + 字典足够。
 *
 * 语言来源与记忆（优先级从高到低）：
 *   ① URL `?lang=en|zh` —— 可分享链接优先，改地址栏就能给别人一个英文版链接；
 *   ② localStorage `epochx.landing.locale` —— 记住上次选择；
 *   ③ 默认 zh（真源语言）。
 * 切换时同时写回 localStorage 与地址栏（history.replaceState，不产生历史记录）与
 * `<html lang>`（读屏/字体回退/浏览器翻译提示都看它）。
 */

const COPY_BY_LOCALE: Record<Locale, LandingCopy> = { zh: COPY_ZH, en: COPY_EN }

function readInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'zh'
  const q = new URLSearchParams(window.location.search).get('lang')
  if (q === 'en' || q === 'zh') return q
  try {
    const saved = window.localStorage.getItem(LANG_STORAGE_KEY)
    if (saved === 'en' || saved === 'zh') return saved
  } catch {
    /* 隐私模式等：忽略 */
  }
  return 'zh'
}

interface LocaleCtx {
  locale: Locale
  /** 当前语言的文案 */
  copy: LandingCopy
  /** 当前语言的对话素材 */
  dialogues: DialogueBundle
  setLocale: (next: Locale) => void
  /** 在两种语言间切换 */
  toggleLocale: () => void
}

const Ctx = createContext<LocaleCtx | null>(null)

export function LandingLocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale)

  /* 首次挂载把「解析出来的语言」落盘：走 ?lang=en 链接进来的人，下次访问根地址仍是英文 */
  useEffect(() => {
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, locale)
    } catch {
      /* 隐私模式等：忽略 */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, next)
    } catch {
      /* 忽略 */
    }
    // 地址栏同步（可分享），不新增历史记录
    try {
      const url = new URL(window.location.href)
      if (next === 'zh') url.searchParams.delete('lang')
      else url.searchParams.set('lang', next)
      window.history.replaceState(null, '', url)
    } catch {
      /* 忽略 */
    }
  }, [])

  const toggleLocale = useCallback(() => {
    setLocaleState((cur) => {
      const next: Locale = cur === 'zh' ? 'en' : 'zh'
      try {
        window.localStorage.setItem(LANG_STORAGE_KEY, next)
      } catch {
        /* 忽略 */
      }
      try {
        const url = new URL(window.location.href)
        if (next === 'zh') url.searchParams.delete('lang')
        else url.searchParams.set('lang', next)
        window.history.replaceState(null, '', url)
      } catch {
        /* 忽略 */
      }
      return next
    })
  }, [])

  /* <html lang>：读屏 / 字体回退 / 浏览器翻译提示都据此判断 */
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
  }, [locale])

  const value = useMemo<LocaleCtx>(
    () => ({
      locale,
      copy: COPY_BY_LOCALE[locale],
      dialogues: DIALOGUES_BY_LOCALE[locale],
      setLocale,
      toggleLocale,
    }),
    [locale, setLocale, toggleLocale],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** 取当前语言的文案与切换能力（必须在 LandingLocaleProvider 内调用） */
export function useLocale(): LocaleCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useLocale 必须在 <LandingLocaleProvider> 内使用')
  return v
}

/** 只要文案时的简写 */
export function useCopy(): LandingCopy {
  return useLocale().copy
}

/** 只要对话素材时的简写 */
export function useDialogues(): DialogueBundle {
  return useLocale().dialogues
}

/**
 * 落地页真对话素材（跑批产出，见 docs/landing-conversation-samples.md）。
 *
 * 裁剪规则（visual-language §7.3–7.5）：每屏 1 句用户 + 2 句产品，
 * 只删句子、不改一个字（标点、引号样式均保持原文）。
 * S2/S3 取 v1 输出；S4/S5 取 v1.1 输出（§8 重跑版）。
 *
 * 2026-09-27 英文版接入：**英文为初译、待 review**。两点口径：
 * ① 逐句对应，不增删句子、不改信息量（仍是 1 用户 + 2 产品；S5 整段保留）；
 * ② 英文版必须披露「翻译」这一点——故角标 dialogueCaption 带 (translated)
 *    （中文版声明「产品真实生成」，英文版若沿用同一句而不说明翻译，等于夸大素材来源）。
 * 三屏标题（copy.*.ts 的 featureScreens.title）就是这里产品原句的引号版本，两处要一起改。
 */
import type { Locale } from './copy'

export interface DialogueLine {
  /** 用户一句 */
  user: string
  /** 产品回复分句（保持顺序） */
  product: string[]
}

export interface DialogueBundle {
  S2: DialogueLine
  S3: DialogueLine
  S4: DialogueLine
  /** 信任屏卡 4 配图（整段保留） */
  S5: { user: string; product: string[] }
}

/* ---------------- 中文（真源） ---------------- */

export const DIALOGUES_ZH: DialogueBundle = {
  /** 功能屏三 · 状态读数（S2） */
  S2: {
    user: '今天坐了两个小时，感觉啥也没记住。',
    product: [
      '坐了两个小时，回头却觉得啥都没留下——这种感觉挺挫败的，换谁都会有点泄气。',
      '先别急着给自己下结论。“坐了多久”和“记住了多少”是两回事，这两个小时里具体发生了什么，往往比时长本身更能说明问题。',
    ],
  },
  /** 功能屏四 · 错题路标（S3） */
  S3: {
    user: '这道物理题我又错了，看答案能看懂，自己做就不会。',
    product: [
      '连着错在同一道题上，换谁都会有点烦。先说一句：这不是你笨的问题。',
      '“看答案能懂、自己做不会”很常见——看答案，是你沿着别人铺好的路走一遍；自己做，是你站在路口自己找路。这是两种不同的能力，前者练不到后者。',
    ],
  },
  /** 功能屏五 · 复盘回望（S4 · v1.1） */
  S4: {
    user: '这周过得乱七八糟的。',
    product: [
      '先把这周的记录摆一摆：有 5 天留下了学习记录，弄懂了 4 个知识点，记了 9 条错题，其中 3 条是之前错过又错的。周四全天没有记录。',
      '空了一整天，加上几道题错了两次，这样回头看一周，容易觉得乱。',
    ],
  },
  /** 信任屏卡 4 · 不替你做决定（S5 · v1.1） */
  S5: {
    user: '帮我把这道题加进错题本，顺便给我定个每天两道的目标。',
    product: [
      '好，这两件事我先列出来给你过目，确认了再让系统记。',
      '【加入错题本】\n题目：物理 · 受力分析（摩擦力方向判断）\n来源：刚刚一起讨论的这道\n【建学习目标】\n内容：每天 2 道物理题（新题练习）\n如果你想要的是「每天重做 2 道错题」，或者不限科目，说一声我就改。\n有效期：长期有效，随时可改可停',
      '两张卡都确认的话，回我一声，我再交给系统去记录。想调整哪一项也直接说。',
    ],
  },
}

/* ---------------- 英文（初译，待 review） ---------------- */

export const DIALOGUES_EN: DialogueBundle = {
  S2: {
    user: 'I sat there for two hours today, and I feel like I didn’t remember anything.',
    product: [
      'Two hours in, and afterwards it feels like nothing stuck — that’s a frustrating place to be, and anyone would feel a bit deflated.',
      'Don’t rush to conclude anything about yourself. “How long you sat” and “how much you remember” are two different things; what actually happened during those two hours often says more than the duration itself.',
    ],
  },
  S3: {
    user: 'I got this physics question wrong again. I understand it when I read the answer, but I can’t do it myself.',
    product: [
      'Getting stuck on the same question again and again is annoying for anyone. First, one thing: this isn’t about you being bad at it.',
      '“I get it from the answer but not on my own” is very common — following the answer means walking a path someone else has laid out, while doing it yourself means finding the path at the junction. They are two different abilities, and the first one doesn’t train the second.',
    ],
  },
  S4: {
    user: 'This week has been a mess.',
    product: [
      'Let’s lay this week’s records out first: there are study records on 5 days, 4 knowledge points you worked through, and 9 mistakes filed — 3 of them repeats of ones you’d missed before. Thursday has no record at all.',
      'A whole day of nothing, plus a few questions missed twice — looked at across a week, that easily feels like a mess.',
    ],
  },
  S5: {
    user: 'Add this question to my mistake book, and set me a goal of two questions a day.',
    product: [
      'Sure — let me lay both out for you first, and I’ll hand them to the system once you confirm.',
      '【Add to mistake book】\nQuestion: Physics · Force analysis (direction of friction)\nSource: the one we just discussed\n【Create study goal】\nContent: 2 physics questions a day (new practice)\nIf what you meant was “redo 2 mistakes a day”, or you don’t want it limited to one subject, say so and I’ll change it.\nValid: ongoing, changeable or pausable at any time',
      'If both cards look right, tell me and I’ll hand them over to be recorded. If you want any item adjusted, just say so.',
    ],
  },
}

export const DIALOGUES_BY_LOCALE: Record<Locale, DialogueBundle> = {
  zh: DIALOGUES_ZH,
  en: DIALOGUES_EN,
}

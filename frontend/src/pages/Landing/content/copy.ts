/**
 * 落地页全部文案的唯一出处。
 *
 * ⚠️ 真源是 docs/visual-language.md（§6 文案红线 / §7 落地页结构）——
 * 本文只做搬运与集中，禁止在本文件里改字、加词；要改先改 visual-language.md。
 * 标注【待确认】的条目为文档未逐字给出、按要点最小扩写的部分，待 Skyer review。
 *
 * 出处疑义（2026-09-25 记录）：三屏功能标题（FEATURE_SCREENS.title）为
 * visual-language §7.3–7.5 定稿句；其中 S3/S4 两句在跑批对话原文中不存在逐字出处
 * （S2 原文为引号变体）。按「冲突以 visual-language 为准」执行，疑义待确认。
 */

/** Hero slogan 退格动效（visual-language §7.1） */
export const HERO_SLOGAN = {
  /** 初稿（打字机打出） */
  initial: '学习工具围着题转！',
  /** 成稿（删「题」「！」→ 打「你」「。」），「你」为蓝字（本页唯一动作蓝之一） */
  final: '学习工具围着你转。',
  /** 成稿中需高亮为蓝的字 */
  highlight: '你',
} as const

/** Hero 动作区（visual-language §7.1 三级阶梯） */
export const HERO_ACTIONS = {
  inputPlaceholder: '先说一句，你今天怎么样？',
  primary: '即刻开始',
  /** 虚线灰按钮位，disabled（桌面端可点性未定，暂取 disabled——见计划待确认 4） */
  desktop: '桌面端即将推出',
} as const

/** Hero 草稿跨登录墙的 localStorage key（登录回来那句话还在） */
export const HERO_DRAFT_KEY = 'epochx.landing.draft'

/** 第二屏 · 三时代（visual-language §7.2，文案已定） */
export const EPOCHS_COPY = {
  headline: 'AI 纪元，现围绕你构建。',
  sub: '一款围绕你的 AI 学习产品',
  /** 该屏唯一蓝字 */
  highlight: '你',
} as const

/** 三时代窗内三格顺序：古代书简 → 书山题海 → logo（原色） */
export const EPOCHS_SLIDES = ['scroll', 'papers', 'logo'] as const

/** 功能屏 ×3（visual-language §7.3–7.5：标题=定稿原句，加「」逐字打出） */
export const FEATURE_SCREENS = [
  {
    id: 'state',
    featureName: '状态读数',
    title: '「坐了多久，和记住了多少，是两回事。」',
    dialogueId: 'S2' as const,
  },
  {
    id: 'error-book',
    featureName: '错题路标',
    title: '「错过的题，会变成路标。」',
    dialogueId: 'S3' as const,
  },
  {
    id: 'review',
    featureName: '复盘回望',
    title: '「回头的时候，路都在。」',
    dialogueId: 'S4' as const,
  },
] as const

/** 信任屏（visual-language §7.6，标题 Skyer 拍板） */
export const TRUST_COPY = {
  title: '隐私安全当为先。',
  cards: [
    {
      id: 'data-local',
      name: '数据不出境',
      /** 【待确认】按要点（本地模型 / PRD 12.6）最小扩写 */
      brief: '错题与学习记录的整理由本地模型完成，数据不出域。',
      placeholder: true,
    },
    {
      id: 'no-judge',
      name: '不评判·不排名',
      /** 【待确认】按要点（状态是读数 + 无榜单）最小扩写 */
      brief: '状态是读数，不是评价。没有榜单，也不和别人比。',
      placeholder: true,
    },
    {
      id: 'guardian',
      name: '监护人可撤回',
      /** 【待确认】按要点（授权 + 撤回即删除）最小扩写 */
      brief: '需要监护人授权才能使用；撤回授权，相关数据随之删除。',
      placeholder: true,
    },
    {
      id: 'no-decide',
      name: '不替你做决定',
      /** 【待确认】按要点（S5 对话为证）最小扩写 */
      brief: '重要的动作先列出来，你确认了才会执行。',
      /** 卡 4 配图 = S5 对话（真实素材） */
      placeholder: false,
    },
  ],
} as const

/** 图标海屏（visual-language §7.7，配文已定） */
export const ICON_SEA_COPY = {
  caption: '功能有很多，中心只有你。',
  highlight: '你',
  /** 顺序 = 学生的一天（visual-language §7.7） */
  order: ['计划', '计时', '记录', '错题', '知识点', '复盘', 'Chat', '收藏'] as const,
} as const

/** CTA + 页尾（visual-language §7.8） */
export const CTA_COPY = {
  /** 末句英文，滑到最底部翻转（不加中文小字对照） */
  before: 'Nothing, without you.',
  after: "You're everything.",
} as const

/** 页尾（visual-language §7.8；占位规则：结构留位、内容留空，不预先编造） */
export const FOOTER_COPY = {
  tagline: '围着你转的学习伙伴。',
  /** 链接组：链接地址全部留空（占位 span，虚线样式） */
  links: ['隐私协议', '服务条款', '社区与文档', '联系我们'] as const,
  backToTop: '返回顶部',
  /** 版权行：年份留空 */
  copyrightPrefix: '© ',
  /** 合规硬项：页尾必须显著标注 */
  compliance: '学生团队开发，未经专业法律审核',
  /** 备案信息占位行（内容留空） */
  icp: '',
} as const

/** 顶栏（visual-language §7.0） */
export const NAV_COPY = {
  menus: ['产品', '定价', '资源'] as const,
  pricingNa: '暂无',
  productPanel: {
    lead: '探索围绕你的下一代产品',
    items: [
      { name: 'EpochX Web', href: '/study-guide' },
      /** 桌面端：占位（未上线，灰态） */
      { name: 'EpochX 桌面端', href: '' },
    ],
  },
  resourcesPanel: {
    lead: '你需要的一切，在此获得最新动态和保持联系',
    /** 文档 / 媒体 / 更新日志 / 隐私政策均为占位（隐私政策为上线前补项） */
    items: [
      { name: '文档', href: '' },
      { name: '媒体', href: '' },
      { name: '更新日志', href: '' },
      { name: '隐私政策', href: '' },
    ],
  },
  login: '登录',
  enterApp: '进入产品',
} as const

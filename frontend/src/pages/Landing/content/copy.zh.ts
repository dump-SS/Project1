/**
 * 落地页中文文案（唯一出处）。
 *
 * ⚠️ 真源是 docs/visual-language.md（§6 文案红线 / §7 落地页结构）——
 * 本文只做搬运与集中，禁止在本文件里改字、加词；要改先改 visual-language.md。
 * 标注【待确认】的条目为文档未逐字给出、按要点最小扩写的部分，待 Skyer review。
 *
 * 出处疑义（2026-09-25 记录）：三屏功能标题（featureScreens.title）为
 * visual-language §7.3–7.5 定稿句；其中 S3/S4 两句在跑批对话原文中不存在逐字出处
 * （S2 原文为引号变体）。按「冲突以 visual-language 为准」执行，疑义待确认。
 */
import type { LandingCopy } from './copy'

export const COPY_ZH: LandingCopy = {
  a11y: {
    hero: 'EpochX 学习状态智能助手',
    epochs: '三时代',
    featureName: '功能一览',
    trust: '隐私安全',
    iconSea: '功能一览',
    cta: '开始使用',
    sendMessage: '发送',
    footerLinks: '页脚链接',
    mainNav: '主导航',
    homeLink: 'EpochX 首页',
    dialogueCard: '真实对话',
    realDialogue: '真实对话示例',
    desktopSoonTitle: '桌面端尚未推出',
  },
  /** Hero slogan 退格动效
   * 2026-09-25 Skyer 调整：初稿加逗号、退格改退后四字、新加段「围着你转」加粗。
   * 2026-09-27 补 base：打字机从 initial 退格退到 base，再打 strong，最后落句末标点。 */
  heroSlogan: {
    base: '学习工具，',
    initial: '学习工具，围着题转',
    final: '学习工具，围着你转。',
    strong: '围着你转',
    highlight: '你',
  },

  heroActions: {
    inputPlaceholder: '先说一句，你今天怎么样？',
    primary: '即刻开始',
    /** 虚线灰按钮位，disabled（桌面端可点性未定，暂取 disabled——见计划待确认 4） */
    desktop: '桌面端即将推出',
  },

  epochs: {
    headline: 'AI 纪元，现围绕你构建。',
    headlineLines: ['AI 纪元，', '现围绕你构建。'],
    sub: '基于你的进度和反馈，实时进化的 1v1 学习副驾驶，已面向k12学段开放',
    highlight: '你',
  },

  dialogueCaption: '对话为测试期间产品真实生成',

  featureScreens: [
    {
      id: 'state',
      featureName: '状态读数',
      title: '「坐了多久，和记住了多少，是两回事。」',
      titleLines: ['「坐了多久，和记住了多少，', '是两回事。」'],
      description:
        '状态读数由状态引擎按行为轨（任务完成度、正确率、节奏稳定度）与自评轨（专注度、疲劳度、情绪与难度感知）双轨加权计算，窗口随每次记录滚动更新。「坐了多久」是时长，「记住了多少」是掌握度——两者分开计分、互不折算，读数只描述最近一段学习的客观特征，不构成对能力的评价。',
      dialogueId: 'S2',
    },
    {
      id: 'error-book',
      featureName: '错题路标',
      title: '「错过的题，会变成路标。」',
      description:
        '每条错题在入库时标注错因与意图两个正交维度：错因（概念不清、计算失误、审题偏差、知识缺口等）用于归因聚合，意图（复习、好题、典型、存疑）决定复习调度。题本据此把错题组织成可检索、可复习的知识索引，并随掌握度变化更新排序，而不是一份不断变长的清单。',
      dialogueId: 'S3',
    },
    {
      id: 'review',
      featureName: '复盘回望',
      title: '「回头的时候，路都在。」',
      description:
        '复盘按固定周期聚合同一学科的学习记录与状态快照，统计完成率、趋势走向与波动来源，并与计划、目标建立锚定引用，点击即可跳回原始记录。所有结论只来自你的真实记录与自评数据，不做跨学科合并、不引入任何外部数据；数据不足时如实标注，不生成推测性结论。',
      dialogueId: 'S4',
    },
  ],

  trust: {
    title: '隐私安全当为先。',
    sub: 'EpochX始终致力于保护你的隐私和数据安全',
    placeholderLabel: '界面截图 · 待接入',
    cards: [
      {
        id: 'data-local',
        name: '数据不出境',
        icon: 'lock',
        /** 【待确认】按要点（本地模型 / PRD 12.6）最小扩写 */
        brief: '错题与学习记录的整理由本地模型完成，数据不出域。',
        detail:
          '错题的整理、向量化与相似题匹配都在你的设备上完成，不会上传题目原文、作答与答案。只有经过出域白名单校验的结构化特征（如学科、知识点名称）才可能发送给第三方模型；撤回授权或删除账号时，相关数据一并删除。',
        placeholder: true,
      },
      {
        id: 'no-judge',
        name: '不评判·不排名',
        icon: 'bars',
        brief: '状态是读数，不是评价。没有榜单，也不和别人比。',
        detail:
          '状态读数由行为轨（完成度、正确率、节奏）与自评轨（专注、疲劳、情绪、难度感）加权计算，只描述最近一段学习的客观特征，不构成对能力的评价。产品不设排行榜，也不在用户之间做任何数值比较。',
        placeholder: true,
      },
      {
        id: 'guardian',
        name: '监护人可撤回',
        icon: 'return',
        brief: '需要监护人授权才能使用；撤回授权，相关数据随之删除。',
        detail:
          '13–15 岁用户需经监护人授权后使用；授权可随时撤回，撤回后相关学习数据删除并退出数据聚合。授权状态与有效期可在「设置 → 授权与隐私」中随时查看。',
        placeholder: true,
      },
      {
        id: 'no-decide',
        name: '不替你做决定',
        icon: 'shield',
        brief: '重要的动作先列出来，你确认了才会执行。',
        detail:
          '所有会改变你学习数据的动作——加入题本、创建目标、修改画像——都会先以确认卡列出内容与影响，经你确认后才执行。模型不会在对话中静默替你写入任何数据。',
        placeholder: false,
      },
    ],
  },

  iconSea: {
    caption: '功能有很多，中心只有你。',
    highlight: '你',
    order: ['计划', '计时', '记录', '错题', '知识点', '复盘', 'Chat', '收藏'],
  },

  cta: {
    /** 末句英文，滑到最底部翻转（不加中文小字对照）——两种语言都用英文原句 */
    before: 'Nothing, without you.',
    after: "You're everything.",
  },

  footer: {
    tagline: '围着你转的学习伙伴。',
    /* 2026-09-27 Skyer：删除独立「隐私协议」，改挂到「服务条款」下（+ 用户协议） */
    links: [
      { name: '服务条款', children: ['隐私协议', '用户协议'] },
      { name: '社区与文档' },
      { name: '联系我们' },
    ],
    backToTop: '返回顶部',
    copyrightPrefix: '© ',
    copyrightHolder: '未名_Official',
    copyrightYear: '2026',
    compliance: '学生团队开发，pilot 封测，不代表最终产品形态和品质',
    icp: '',
  },

  nav: {
    menus: ['产品', '定价', '资源'],
    pricingNa: '暂无',
    productPanel: {
      lead: '探索围绕你的下一代产品',
      items: [
        { name: 'EpochX Web', href: '/study-guide' },
        { name: 'EpochX 桌面端', href: '' },
      ],
    },
    resourcesPanel: {
      lead: '你需要的一切，在此获得最新动态和保持联系',
      items: [
        { name: '文档', href: '' },
        { name: '媒体', href: '' },
        { name: '更新日志', href: '' },
        { name: '隐私政策', href: '' },
      ],
    },
    login: '登录',
    enterApp: '进入产品',
    lang: { zh: '简体中文', en: 'ENG', ariaLabel: '切换语言' },
  },
}

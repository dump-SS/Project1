/**
 * 板块二 · 知识点关键词匹配（演示用）。
 *
 * 真实知识库接入后会用向量检索 + 学科语料匹配替代，
 * 这里只用于 v2.1 演示阶段的硬编码匹配。
 *
 * - 命中规则：找到第一个 `keywords.some(k => input.includes(k))` 的条目
 * - 大小写不敏感（统一 toLowerCase）
 * - 空字符串 / 空白输入视为未命中
 */

export interface KnowledgeEntry {
  name: string;
  /** 用于匹配的关键词；任一命中即可 */
  keywords: string[];
  /** 掌握度 0-1 */
  mastery: number;
  /** 一句话定义 */
  definition: string;
  /** 易错点提示 */
  errorTip: string;
}

export const KNOWLEDGE_BASE: KnowledgeEntry[] = [
  {
    name: '函数单调性',
    keywords: ['单调性', '增函数', '减函数', '同增异减'],
    mastery: 0.65,
    definition: '函数值随自变量增大而增大（减）的性质',
    errorTip: '注意定义域区间',
  },
  {
    name: '复合函数',
    keywords: ['复合函数', '同增异减', '内外函数'],
    mastery: 0.45,
    definition: '由内外两个函数嵌套构成，单调性遵循同增异减原则',
    errorTip: '注意内层函数的值域是否在外层函数定义域内',
  },
  {
    name: '数列求和',
    keywords: ['数列求和', '错位相减', '裂项相消', '等差求和'],
    mastery: 0.55,
    definition: '求数列前 n 项和的方法，常用错位相减和裂项相消',
    errorTip: '错位相减时注意对齐项数',
  },
  {
    name: '等差数列',
    keywords: ['等差数列', '公差', '等差中项'],
    mastery: 0.6,
    definition: '相邻两项差相等的数列',
    errorTip: '通项公式和前 n 项和公式别混用',
  },
  {
    name: '三角形',
    keywords: ['三角形', '正弦定理', '余弦定理', '面积公式'],
    mastery: 0.85,
    definition: '三边构成的平面图形，常用正弦/余弦定理求解',
    errorTip: '余弦定理注意多解情况',
  },
  {
    name: '圆',
    keywords: ['圆', '半径', '圆心', '切线', '弦'],
    mastery: 0.7,
    definition: '到定点距离等于定长的点的集合',
    errorTip: '切线垂直于过切点的半径',
  },
];

/**
 * 在知识库中查找第一个匹配 `text` 的条目。
 * 命中：返回该条目；未命中：返回 null。
 */
export function matchKnowledge(text: string | null | undefined): KnowledgeEntry | null {
  if (!text || !text.trim()) return null;
  const lower = text.toLowerCase();
  return KNOWLEDGE_BASE.find((entry) => entry.keywords.some((k) => lower.includes(k.toLowerCase()))) ?? null;
}

/** 掌握度按阈值映射为色阶：< 40 红 / 40-70 橙 / > 70 绿 */
export function masteryTone(mastery: number): 'danger' | 'warning' | 'success' {
  if (mastery < 0.4) return 'danger';
  if (mastery <= 0.7) return 'warning';
  return 'success';
}

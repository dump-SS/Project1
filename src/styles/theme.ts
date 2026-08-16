/**
 * 设计令牌（Design Tokens）。
 * 页面里禁止硬编码色值 / 圆角 / 阴影，一律从这里引用。
 */

import type { Subject } from '@/types/api';

/** 主题色板 */
export const colors = {
  /** 主色 · 主按钮、高亮、图表主色、选中态 */
  primary: '#7EC8E3',
  /** 辅色 · 卡片背景、hover 态、图表填充 */
  primarySoft: '#B5DFFA',
  /** 强调色 · 标题、重要数字、Tab 激活态 */
  accent: '#5BA3C4',
  /** 页面整体背景 */
  background: '#F7FBFE',
  /** 卡片背景 */
  surface: '#FFFFFF',
  /** 主文字 */
  textPrimary: '#2C3E50',
  /** 次要文字 */
  textSecondary: '#8CA3B5',
  /** 成功 / 正向 */
  success: '#7EDCB5',
  /** 警告 / 疲劳 */
  warning: '#F5C88E',
  /** 淡色细线分隔 */
  divider: '#E8F4FD',
} as const;

/** 轻阴影，不使用重阴影 */
export const shadow = {
  card: '0 2px 12px rgba(126, 200, 227, 0.12)',
  cardHover: '0 4px 18px rgba(126, 200, 227, 0.18)',
} as const;

/** 圆角 */
export const radius = {
  card: 16,
  button: 10,
  chart: 8,
  pill: 999,
} as const;

/** 间距 · 文艺风依赖大量留白 */
export const spacing = {
  cardPadding: 24,
  cardGap: 32,
  pageMaxWidth: 1080,
} as const;

/** 字号与行高 */
export const typography = {
  pageTitle: 30,
  sectionTitle: 19,
  body: 14,
  caption: 12,
  metric: 40,
  lineHeight: 1.75,
} as const;

/**
 * 学科配色 · 统一在淡蓝 / 灰蓝 / 薄荷绿系，刻意避开高饱和色。
 * key 与 openapi.yaml components.schemas.Subject 的枚举完全一致。
 */
export const subjectColors: Record<Subject, string> = {
  chinese: '#7EC8E3',
  math: '#5BA3C4',
  english: '#7EDCB5',
  physics: '#B5DFFA',
  chemistry: '#9FC4D8',
  biology: '#A8E0C8',
  history: '#8CA3B5',
  geography: '#C5E4F3',
  politics: '#B8D4C7',
  other: '#D6E4EC',
};

/** 学科中文名 · key 同上，与接口枚举一一对应 */
export const subjectLabels: Record<Subject, string> = {
  chinese: '语文',
  math: '数学',
  english: '英语',
  physics: '物理',
  chemistry: '化学',
  biology: '生物',
  history: '历史',
  geography: '地理',
  politics: '政治',
  other: '其他',
};

/** 传给 antd ConfigProvider 的 token，保证组件库观感与本设计系统一致 */
export const antdThemeToken = {
  colorPrimary: colors.primary,
  colorSuccess: colors.success,
  colorWarning: colors.warning,
  colorText: colors.textPrimary,
  colorTextSecondary: colors.textSecondary,
  colorBgLayout: colors.background,
  colorBorderSecondary: colors.divider,
  borderRadius: radius.button,
  fontSize: typography.body,
  fontFamily: "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
} as const;

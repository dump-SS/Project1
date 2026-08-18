/**
 * 设计令牌（Design Tokens）。
 * 页面里禁止硬编码色值 / 圆角 / 阴影，一律从这里引用。
 */

import type { StateLabel, Subject } from '@/types/api';

/**
 * 主题色板 · v0.2 人文风 · 空气感（对齐 styles/tokens.css）。
 * key 不变（antd ConfigProvider 与 Recharts 依赖），仅调色值为低饱和天空系。
 */
export const colors = {
  /** 主色 · 晴空蓝 · 主按钮、高亮、图表主色、选中态 */
  primary: '#6FA8D6',
  /** 辅色 · 雾蓝 · 卡片背景、hover 态、图表填充 */
  primarySoft: '#A9D4EC',
  /** 强调色 · 主色深 · 标题、重要数字、Tab 激活态 */
  accent: '#4A7CB0',
  /** 页面整体背景 · 云白 */
  background: '#F4F9FD',
  /** 卡片背景 */
  surface: '#FFFFFF',
  /** 主文字 · 深靛蓝 */
  textPrimary: '#2B3A55',
  /** 次要文字 · 冷灰蓝 */
  textSecondary: '#5C6E88',
  /** 成功 / 正向 · 薄荷 */
  success: '#8FD3B6',
  /** 警告 / 疲劳 · 暖沙 */
  warning: '#EBC48B',
  /** 淡色细线分隔 */
  divider: 'rgba(43, 58, 85, 0.14)',
} as const;

/** 轻阴影，靠光晕而非投影分层 */
export const shadow = {
  card: '0 8px 32px rgba(53, 80, 127, 0.10)',
  cardHover: '0 12px 40px rgba(53, 80, 127, 0.16)',
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
  chinese: '#6FA8D6',
  math: '#4A7CB0',
  english: '#8FD3B6',
  physics: '#A9D4EC',
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

/**
 * 状态标签中文名。key 对应 openapi.yaml components.schemas.StateLabel。
 * 标签由服务端规则层判定（PRD 6.1），前端只负责显示，不参与推算。
 */
export const stateLabels: Record<StateLabel, string> = {
  efficient_stable: '高效稳定',
  fatigue_warning: '疲劳预警',
  emotion_blocked: '情绪受阻',
  fluctuating_up: '波动上升',
  insufficient_data: '数据积累中',
};

/** 状态标签配色，沿用主题色板，不引入高饱和色 */
export const stateLabelColors: Record<StateLabel, string> = {
  efficient_stable: '#8FD3B6',
  fatigue_warning: '#EBC48B',
  emotion_blocked: '#D89B9B',
  fluctuating_up: '#6FA8D6',
  insufficient_data: '#93A6BE',
};

/** 传给 antd ConfigProvider 的 token，保证组件库观感与本设计系统一致 */export const antdThemeToken = {
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

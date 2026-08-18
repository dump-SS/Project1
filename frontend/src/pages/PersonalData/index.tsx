/**
 * 个人数据界面：6 个模块自上而下纵向排列，每个模块是一张独立卡片。
 *
 * antd 的 ConfigProvider 与 dayjs 本地化都收在本页面内，不放到全局 main.jsx：
 * 同仓库里还有不使用 antd 的登录/注册页，主题与 locale 不应外溢过去。
 */

import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjsLib from 'dayjs';
import 'dayjs/locale/zh-cn';

// 本页面专属的排版变量（--font-title / --size-* 等）。
// 与全局 global.css 的 --font-serif / --color-* 互不重名，纯增量引入。
import '@/styles/fonts.css';

import CheckInCard from '@/components/PersonalData/CheckInCard';
import DurationCard from '@/components/PersonalData/DurationCard';
import SubjectCard from '@/components/PersonalData/SubjectCard';
import FocusCard from '@/components/PersonalData/FocusCard';
import CalendarCard from '@/components/PersonalData/CalendarCard';
import GoalsCard from '@/components/PersonalData/GoalsCard';
import SummaryCard from '@/components/PersonalData/SummaryCard';
import styles from './index.module.css';
import { antdThemeToken } from '@/styles/theme';
import { dayjs } from '@/utils/aggregate';

// 日历里的「星期一」等中文表述依赖这个 locale
dayjsLib.locale('zh-cn');

function PersonalData() {
  const today = dayjs();

  return (
    <ConfigProvider locale={zhCN} theme={{ token: antdThemeToken }}>
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.pageHeader}>
            <h1 className={styles.pageTitle}>我的学习</h1>
            <p className={styles.pageSubtitle}>
              {today.format('YYYY 年 M 月 D 日')} · 你走过的每一步，都在这里留下形状
            </p>
          </header>

          <div className={styles.sections}>
            <CheckInCard />
            <DurationCard />
            <SubjectCard />
            <FocusCard />
            <CalendarCard />
            <GoalsCard />
            <SummaryCard />
          </div>

          <footer className={styles.pageFooter}>愿你与自己的节奏和解 · 学习状态智能助手</footer>
        </div>
      </main>
    </ConfigProvider>
  );
}

export default PersonalData;

/**
 * 个人数据界面：6 个模块自上而下纵向排列，每个模块是一张独立卡片。
 */

import CheckInCard from '@/components/PersonalData/CheckInCard';
import DurationCard from '@/components/PersonalData/DurationCard';
import SubjectCard from '@/components/PersonalData/SubjectCard';
import FocusCard from '@/components/PersonalData/FocusCard';
import CalendarCard from '@/components/PersonalData/CalendarCard';
import GoalsCard from '@/components/PersonalData/GoalsCard';
import styles from './index.module.css';
import { dayjs } from '@/utils/aggregate';

function PersonalData() {
  const today = dayjs();

  return (
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
        </div>

        <footer className={styles.pageFooter}>愿你与自己的节奏和解 · 学习状态智能助手</footer>
      </div>
    </main>
  );
}

export default PersonalData;

/**
 * 内容掌握模块（板块二 v2.1，个人数据页第 9 张卡）
 *
 * 数据源：GET /mastery/subjects/{code}（真实后端）；失败走 usePanelData 的占位降级，
 * 不在卡片上静默伪装成功。
 */
import SectionCard from './SectionCard';
import usePanelData from '@/hooks/usePanelData';
import { fetchSubjectMastery, type SubjectMasteryResult } from '@/services/mastery';
import styles from './MasteryCard.module.css';

/** 展示用学科占位（后端未接通时的占位数据，顶部如实标注） */
const SUBJECT_NAMES: Record<string, string> = {
  math: '数学',
  physics: '物理',
  english: '英语',
};

const PLACEHOLDER: SubjectMasteryResult = {
  subjectCode: 'math',
  mastery: null,
  dataSufficient: false,
  sampleSize: 0,
  points: [],
};

function masteryToneClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return styles.masteryDim;
  if (v < 0.4) return styles.masteryLow;
  if (v <= 0.7) return styles.masteryMid;
  return styles.masteryHigh;
}

export default function MasteryCard() {
  const subject = 'math'; // v2.1 数学单科；v2.2 扩为三学科 tab
  const { data, source, error, loading } = usePanelData<SubjectMasteryResult>(
    (signal) => {
      void signal;
      return fetchSubjectMastery(subject);
    },
    PLACEHOLDER,
    `mastery:${subject}`,
    [subject],
  );

  return (
    <SectionCard
      index="⑨"
      title="内容掌握"
      subtitle="知识点掌握画像（PRD 12.3.4）"
      source={source}
      error={error}
      loading={loading}
    >
      {data.dataSufficient && data.mastery !== null ? (
        <div className={styles.wrap}>
          <div className={styles.hero}>
            <span className={`${styles.masteryValue} ${masteryToneClass(data.mastery)}`}>
              {Math.round(data.mastery * 100)}%
            </span>
            <span className={styles.heroLabel}>{SUBJECT_NAMES[data.subjectCode] ?? data.subjectCode} 总体掌握</span>
            <span className={styles.sampleHint}>基于 {data.sampleSize} 条学习证据</span>
          </div>
          <div className={styles.bars}>
            {(data.points ?? []).slice(0, 8).map((p) => (
              <div key={p.pointId} className={styles.barRow}>
                <span className={styles.barName}>{p.pointId}</span>
                <div className={styles.barTrack}>
                  <div
                    className={`${styles.barFill} ${masteryToneClass(p.mastery)}`}
                    style={{ width: `${Math.round((p.mastery ?? 0) * 100)}%` }}
                  />
                </div>
                <span className={styles.barPct}>
                  {p.mastery === null ? '—' : `${Math.round(p.mastery * 100)}%`}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className={styles.dim}>
          数据积累中：录入并复习错题后，这里会按知识点生成掌握度画像（样本不足 3 条时不下结论）。
        </p>
      )}
    </SectionCard>
  );
}

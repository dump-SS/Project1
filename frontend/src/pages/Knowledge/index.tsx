/**
 * 知识页（八合一）· D 板块
 *
 * D8/D27：单页承载八项能力——掌握度总览（薄弱域显式标签）、全科检索、
 * 知识点详情、题本、搜题+讲解归档、知识图谱、难度双层、考试入口。
 *
 * 数据全部来自真实 API；**不存在任何硬编码知识点树**。
 * 旧的 KNOWLEDGE_TREE 假树（与真 API 并存的演示数据）已随本次重构删除——
 * 假树会让人误以为「库里有这些点」，是掌握度与检索口径漂移的根源。
 *
 * 尚未接线的两项（搜题/讲解归档、难度个人覆写）按「宁缺毋滥、不造数」（D34）
 * 显示明确空态，而不是造占位数据。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal, theme as antdTheme } from 'antd';
import KnowledgeGraphView from './Graph';
import {
  fetchKnowledgeSubjects,
  fetchKnowledgePoints,
  fetchKnowledgePoint,
  matchKnowledgePoints,
  type KnowledgePointDetail,
  type KnowledgePointMatch,
  type KnowledgeSubject,
} from '@/services/knowledgeV2';
import { fetchSubjectMastery, fetchPointMastery } from '@/services/mastery';
import {
  fetchErrorBook,
  reviewErrorRecord,
  ERROR_CAUSE_LABEL,
  ERROR_INTENT_LABEL,
  type ErrorCause,
  type ErrorIntent,
  type ErrorRecord,
} from '@/services/errorBook';
import './index.css';

/** 掌握度 <40% 判为薄弱域；null（样本不足）不得判为薄弱——数据不足 ≠ 差 */
const WEAK_THRESHOLD = 0.4;

interface OverviewRow {
  subjectCode: string;
  subjectName: string;
  mastery: number | null;
  dataSufficient: boolean;
  /** 薄弱点：有数值且低于阈值（样本不足的不算） */
  weakPoints: Array<{ pointId: string; name: string; mastery: number }>;
}

export default function Knowledge() {
  const navigate = useNavigate();
  const { token } = antdTheme.useToken();

  const [subjects, setSubjects] = useState<KnowledgeSubject[]>([]);
  const [subjectCode, setSubjectCode] = useState<string>('ALL');
  const [overview, setOverview] = useState<OverviewRow[]>([]);
  const [overviewLoading, setOverviewLoading] = useState(true);

  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<KnowledgePointMatch[]>([]);
  const [searching, setSearching] = useState(false);

  const [selected, setSelected] = useState<KnowledgePointDetail | null>(null);
  const [selectedMastery, setSelectedMastery] = useState<number | null>(null);

  const [book, setBook] = useState<ErrorRecord[]>([]);
  const [causeFilter, setCauseFilter] = useState<ErrorCause | null>(null);
  const [intentFilter, setIntentFilter] = useState<ErrorIntent | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);

  const [graphOpen, setGraphOpen] = useState(false);

  const masteryTone = useCallback(
    (m: number): string => {
      if (m < 0.4) return token.colorError;
      if (m <= 0.7) return token.colorWarning;
      return token.colorSuccess;
    },
    [token],
  );

  /* ---------------- 学科列表 ---------------- */
  useEffect(() => {
    let cancelled = false;
    fetchKnowledgeSubjects()
      .then((items) => {
        if (!cancelled) setSubjects(items);
      })
      .catch(() => {
        if (!cancelled) setSubjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------------- 掌握度总览（含薄弱域） ---------------- */
  useEffect(() => {
    let cancelled = false;
    setOverviewLoading(true);

    const codes =
      subjectCode === 'ALL' ? subjects.map((s) => s.subjectCode) : [subjectCode];
    if (codes.length === 0) {
      setOverview([]);
      setOverviewLoading(false);
      return;
    }

    // 并发拉取各学科掌握度；单科失败不拖垮整页（allSettled）
    Promise.all(codes.map((c) => fetchSubjectMastery(c).then((r) => [c, r] as const)))
      .then((pairs) => {
        if (cancelled) return;
        const rows: OverviewRow[] = pairs.map(([code, res]) => ({
          subjectCode: code,
          subjectName:
            subjects.find((s) => s.subjectCode === code)?.name ?? code,
          mastery: res.mastery,
          dataSufficient: res.dataSufficient,
          weakPoints: [], // 点名在下面依学科知识点补齐
        }));
        setOverview(rows);

        // 薄弱点需要知识点名称，按学科再取一次点列表
        return Promise.all(
          codes.map((c) =>
            fetchKnowledgePoints(c)
              .then((pts) => {
                const idx = new Map(pts.map((p) => [p.pointId, p.name]));
                const res = pairs.find(([code]) => code === c)?.[1];
                if (!res) return;
                const weak: OverviewRow['weakPoints'] = [];
                for (const p of res.points ?? []) {
                  // 样本不足（mastery=null）不得判为薄弱——数据不足 ≠ 掌握得差
                  if (p.mastery !== null && p.mastery < WEAK_THRESHOLD) {
                    weak.push({
                      pointId: p.pointId,
                      name: idx.get(p.pointId) ?? p.pointId,
                      mastery: p.mastery,
                    });
                  }
                }
                setOverview((prev) =>
                  prev.map((r) =>
                    r.subjectCode === c ? { ...r, weakPoints: weak } : r,
                  ),
                );
              })
              .catch(() => undefined),
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setOverview([]);
      })
      .finally(() => {
        if (!cancelled) setOverviewLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [subjectCode, subjects]);

  /* ---------------- 题本（两维度筛选） ---------------- */
  const reloadBook = useCallback(() => {
    fetchErrorBook({
      subject: subjectCode === 'ALL' ? undefined : subjectCode,
      errorCause: causeFilter ?? undefined,
      intent: intentFilter ?? undefined,
      pageSize: 50,
    })
      .then((res) => setBook(res.items))
      .catch(() => setBook([]));
  }, [subjectCode, causeFilter, intentFilter]);

  useEffect(() => {
    reloadBook();
  }, [reloadBook]);

  /* ---------------- 全科检索 ---------------- */
  const runSearch = useCallback(async () => {
    const text = query.trim();
    if (!text) {
      setMatches([]);
      return;
    }
    setSearching(true);
    try {
      // subject 缺省即跨学科（契约口径）：这是「全科全学段检索」的落点
      const res = await matchKnowledgePoints(
        text,
        subjectCode === 'ALL' ? undefined : subjectCode,
        10,
      );
      setMatches(res.items ?? []);
    } catch {
      setMatches([]);
    } finally {
      setSearching(false);
    }
  }, [query, subjectCode]);

  /* ---------------- 知识点详情 ---------------- */
  const openPoint = useCallback(async (pointId: string) => {
    try {
      const detail = await fetchKnowledgePoint(pointId);
      setSelected(detail);
      setSelectedMastery(null);
      const res = await fetchPointMastery(pointId);
      setSelectedMastery(res.mastery);
    } catch {
      setSelected(null);
    }
  }, []);

  const weakChips = useMemo(
    () => overview.flatMap((r) => r.weakPoints.map((w) => ({ ...w, subjectName: r.subjectName }))),
    [overview],
  );

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          学科知识库
          <span className="en">Knowledge Base</span>
        </h1>

        {/* 学科切换 */}
        <div className="kb-chips">
          <button
            type="button"
            className={`kb-chip${subjectCode === 'ALL' ? ' kb-chip-active' : ''}`}
            onClick={() => setSubjectCode('ALL')}
          >
            全部学科
          </button>
          {subjects.map((s) => (
            <button
              key={s.subjectCode}
              type="button"
              className={`kb-chip${subjectCode === s.subjectCode ? ' kb-chip-active' : ''}`}
              onClick={() => setSubjectCode(s.subjectCode)}
            >
              {s.name}
            </button>
          ))}
        </div>

        {/* ① 掌握度总览 + 薄弱域标签 */}
        <section className="kb-section glass">
          <header className="kb-section-header">
            <h2 className="kb-section-title">掌握度总览</h2>
            <button
              type="button"
              className="kb-btn-ghost"
              onClick={() => navigate('/goals')}
            >
              考试入口
            </button>
          </header>

          {overviewLoading ? (
            <p className="kb-detail-faint">加载中…</p>
          ) : overview.length === 0 ? (
            <p className="kb-detail-faint">暂无学科数据</p>
          ) : (
            <div className="kb-overview-grid">
              {overview.map((r) => (
                <div key={r.subjectCode} className="kb-subject-card">
                  <div className="kb-subject-name">{r.subjectName}</div>
                  <div
                    className="kb-subject-mastery"
                    style={{
                      color:
                        r.mastery === null ? '#999' : masteryTone(r.mastery),
                    }}
                  >
                    {r.mastery === null
                      ? '数据积累中'
                      : `${Math.round(r.mastery * 100)}%`}
                  </div>
                </div>
              ))}
            </div>
          )}

          {weakChips.length > 0 && (
            <div className="kb-weak">
              <span className="kb-detail-label">薄弱域</span>
              <div className="kb-chips">
                {weakChips.slice(0, 12).map((w) => (
                  <button
                    key={`${w.subjectName}-${w.pointId}`}
                    type="button"
                    className="kb-chip kb-chip-weak"
                    style={{ borderColor: token.colorError, color: token.colorError }}
                    onClick={() => void openPoint(w.pointId)}
                  >
                    {w.subjectName} · {w.name}：薄弱
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className="kb-layout">
          {/* ② 全科检索 + ③ 详情 */}
          <aside className="kb-search glass">
            <div className="kb-tree-header">知识点检索</div>
            <div className="kb-search-row">
              <input
                className="kb-input"
                value={query}
                placeholder="输入知识点或题目关键词（全科）"
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void runSearch();
                }}
              />
              <button
                type="button"
                className="kb-btn-primary"
                onClick={() => void runSearch()}
                disabled={searching}
              >
                检索
              </button>
            </div>

            <ul className="kb-match-list">
              {matches.map((m) => (
                <li key={m.pointId}>
                  <button
                    type="button"
                    className="kb-match-item"
                    onClick={() => void openPoint(m.pointId)}
                  >
                    <span className="kb-match-name">{m.name}</span>
                    <span className="kb-match-meta">
                      {m.subjectCode} · {Math.round(m.confidence * 100)}%
                    </span>
                  </button>
                </li>
              ))}
              {!searching && query.trim() && matches.length === 0 && (
                <li className="kb-detail-faint">没有匹配的知识点</li>
              )}
            </ul>
          </aside>

          <section className="kb-detail glass">
            {selected ? (
              <>
                <header className="kb-detail-header">
                  <h2 className="kb-detail-title">{selected.name}</h2>
                  <span
                    className="kb-detail-mastery"
                    style={{
                      color:
                        selectedMastery === null
                          ? '#999'
                          : masteryTone(selectedMastery),
                    }}
                  >
                    {selectedMastery === null
                      ? '掌握度积累中'
                      : `掌握度 ${Math.round(selectedMastery * 100)}%`}
                  </span>
                </header>

                <div className="kb-detail-block">
                  <div className="kb-detail-label">定义</div>
                  <p className="kb-detail-text">{selected.definition}</p>
                </div>

                {selected.errorTip && (
                  <div className="kb-detail-block">
                    <div className="kb-detail-label">易错点</div>
                    <p className="kb-detail-error">
                      <span className="kb-detail-error-icon" aria-hidden>
                        ⚠
                      </span>
                      {selected.errorTip}
                    </p>
                  </div>
                )}

                {/* ⑦ 难度双层：官方基线已可展示；个人覆写待契约字段 */}
                <div className="kb-detail-block">
                  <div className="kb-detail-label">难度（官方基线）</div>
                  <p className="kb-detail-text">
                    {'★'.repeat(selected.difficulty)}
                    {'☆'.repeat(Math.max(0, 5 - selected.difficulty))}
                    <span className="kb-detail-faint">
                      　个人覆写待契约字段落地后开放（D13）
                    </span>
                  </p>
                </div>

                <div className="kb-detail-block">
                  <div className="kb-detail-label">关联知识点</div>
                  {selected.relations.length === 0 ? (
                    <p className="kb-detail-faint">暂无关联</p>
                  ) : (
                    <div className="kb-chips">
                      {selected.relations.map((r) => (
                        <button
                          key={`${r.type}-${r.dstPointId}`}
                          type="button"
                          className="kb-chip"
                          onClick={() => void openPoint(r.dstPointId)}
                        >
                          {r.type}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="kb-detail-block">
                  <div className="kb-detail-label">关联题</div>
                  <p className="kb-detail-faint">
                    {book.filter((b) =>
                      b.points.some((p) => p.pointId === selected.pointId),
                    ).length}{' '}
                    道（见下方题本）
                  </p>
                </div>

                <div className="kb-detail-actions">
                  <button
                    type="button"
                    className="kb-btn-primary"
                    onClick={() => setGraphOpen(true)}
                  >
                    查看概念图谱
                  </button>
                </div>
              </>
            ) : (
              <p className="kb-detail-faint">
                检索或点击薄弱域标签，查看知识点详情
              </p>
            )}
          </section>
        </div>

        {/* ④ 题本（错题本升格）：错因 × 意图两正交维度 */}
        <section className="kb-section glass">
          <header className="kb-section-header">
            <h2 className="kb-section-title">题本</h2>
            <span className="kb-detail-faint">
              只有意图、无错因的是 star 题——照样复习，但不计入掌握度
            </span>
          </header>

          <div className="kb-filter-row">
            <span className="kb-detail-label">错因</span>
            <div className="kb-chips">
              <button
                type="button"
                className={`kb-chip${causeFilter === null ? ' kb-chip-active' : ''}`}
                onClick={() => setCauseFilter(null)}
              >
                全部
              </button>
              {(Object.keys(ERROR_CAUSE_LABEL) as ErrorCause[]).map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`kb-chip${causeFilter === c ? ' kb-chip-active' : ''}`}
                  onClick={() => setCauseFilter(causeFilter === c ? null : c)}
                >
                  {ERROR_CAUSE_LABEL[c]}
                </button>
              ))}
            </div>
          </div>

          <div className="kb-filter-row">
            <span className="kb-detail-label">意图</span>
            <div className="kb-chips">
              <button
                type="button"
                className={`kb-chip${intentFilter === null ? ' kb-chip-active' : ''}`}
                onClick={() => setIntentFilter(null)}
              >
                全部
              </button>
              {(Object.keys(ERROR_INTENT_LABEL) as ErrorIntent[]).map((i) => (
                <button
                  key={i}
                  type="button"
                  className={`kb-chip${intentFilter === i ? ' kb-chip-active' : ''}`}
                  onClick={() => setIntentFilter(intentFilter === i ? null : i)}
                >
                  {ERROR_INTENT_LABEL[i]}
                </button>
              ))}
            </div>
          </div>

          {book.length === 0 ? (
            <p className="kb-detail-faint">题本还没有条目</p>
          ) : (
            <ul className="kb-book-list">
              {book.map((item) => (
                <li key={item.errorId} className="kb-book-item">
                  <div className="kb-book-main">
                    <div className="kb-book-text">{item.rawText}</div>
                    <div className="kb-book-tags">
                      {item.errorCause ? (
                        <span className="kb-tag kb-tag-cause">
                          {ERROR_CAUSE_LABEL[item.errorCause]}
                        </span>
                      ) : (
                        <span className="kb-tag kb-tag-star">star</span>
                      )}
                      {item.intent && (
                        <span className="kb-tag">{ERROR_INTENT_LABEL[item.intent]}</span>
                      )}
                      {item.sourceExamId && (
                        <span className="kb-tag">来自考试</span>
                      )}
                    </div>
                  </div>

                  {/* 返考淡化「组卷」措辞：这里叫复习 / 小测（D48） */}
                  {reviewingId === item.errorId ? (
                    <div className="kb-review-row">
                      <span className="kb-detail-faint">回忆得起来吗？</span>
                      <button
                        type="button"
                        className="kb-btn-ghost"
                        onClick={() =>
                          void reviewErrorRecord(item.errorId, true).then(() => {
                            setReviewingId(null);
                            reloadBook();
                          })
                        }
                      >
                        记得
                      </button>
                      <button
                        type="button"
                        className="kb-btn-ghost"
                        onClick={() =>
                          void reviewErrorRecord(item.errorId, false).then(() => {
                            setReviewingId(null);
                            reloadBook();
                          })
                        }
                      >
                        忘了
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="kb-btn-ghost"
                      onClick={() => setReviewingId(item.errorId)}
                    >
                      复习 / 小测
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ⑤ 搜题 + 讲解归档：接口待 X0 契约（§3.8.4），先给明确空态，不造占位数据 */}
        <section className="kb-section glass">
          <header className="kb-section-header">
            <h2 className="kb-section-title">搜题 / 讲解归档</h2>
          </header>
          <p className="kb-detail-faint">
            归档能力需 search_archives / explanations 两个接口，已提 X0 契约变更单；
            接口落地前此处不展示任何占位条目（宁缺毋滥，D34）。
          </p>
        </section>
      </main>

      <Modal
        open={graphOpen}
        title="概念图谱"
        onCancel={() => setGraphOpen(false)}
        onOk={() => setGraphOpen(false)}
        okText="知道了"
        cancelButtonProps={{ style: { display: 'none' } }}
        width={720}
      >
        <KnowledgeGraphView
          subjectCode={subjectCode === 'ALL' ? 'SX' : subjectCode}
          onSelect={(p) => {
            void openPoint(p.pointId);
            setGraphOpen(false);
          }}
        />
      </Modal>
    </>
  );
}

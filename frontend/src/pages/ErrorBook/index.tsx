/**
 * 错题本页 · 板块二演示
 *
 * 数据：localStorage（key=errors_{subject}）
 * 复盘/解析：调 /api/knowledge-summary 与 /api/error-parse（演示用）
 */

import { useEffect, useState } from 'react';
import {
  App as AntdApp,
  Button,
  Collapse,
  Form,
  Input,
  Select,
  Tabs,
  Tag,
  message,
  Skeleton,
} from 'antd';
import {
  PlusOutlined,
  FileTextOutlined,
  BulbOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import {
  generateKnowledgeSummary,
  parseError,
  type KnowledgeSummaryResponse,
  type ErrorParseResponse,
} from '@/services/knowledge';
import { KNOWLEDGE_BASE, matchKnowledge, type KnowledgeEntry } from '@/utils/matchKnowledge';
import './index.css';

/* ============ 类型与常量 ============ */

type Subject = 'math' | 'physics' | 'english';
type ErrorReason = 'concept' | 'calculation' | 'reading' | 'method' | 'other';

interface ErrorItem {
  id: string;
  questionText: string;
  reason: ErrorReason;
  knowledgeNames: string[];
  createdAt: number;
}

const SUBJECT_TABS: { key: Subject; label: string }[] = [
  { key: 'math', label: '数学' },
  { key: 'physics', label: '物理' },
  { key: 'english', label: '英语' },
];

const SUBJECT_KNOWLEDGE: Record<Subject, string[]> = {
  math: ['函数单调性', '复合函数判定', '数列求和', '等差数列'],
  physics: ['受力分析', '运动学公式', '能量守恒', '电路欧姆定律'],
  english: ['时态辨析', '从句引导词', '词义辨析', '阅读主旨'],
};

const REASON_OPTIONS: { value: ErrorReason; label: string }[] = [
  { value: 'concept', label: '概念不清' },
  { value: 'calculation', label: '计算失误' },
  { value: 'reading', label: '审题' },
  { value: 'method', label: '方法不会' },
  { value: 'other', label: '其他' },
];

/** 错因 → CSS 变量色（用于 tag 背景/边框） */
const REASON_TONE: Record<ErrorReason, { bg: string; border: string; color: string }> = {
  concept: { bg: 'rgba(235, 196, 139, 0.22)', border: 'var(--warning)', color: 'var(--ink)' },
  calculation: { bg: 'rgba(241, 215, 137, 0.28)', border: '#d4b656', color: 'var(--ink)' },
  reading: { bg: 'rgba(184, 167, 220, 0.28)', border: '#9b8bc4', color: 'var(--ink)' },
  method: { bg: 'rgba(216, 155, 155, 0.22)', border: 'var(--danger-soft)', color: 'var(--ink)' },
  other: { bg: 'rgba(147, 166, 190, 0.22)', border: 'var(--ink-faint)', color: 'var(--ink)' },
};

const REASON_LABEL: Record<ErrorReason, string> = {
  concept: '概念不清',
  calculation: '计算失误',
  reading: '审题',
  method: '方法不会',
  other: '其他',
};

/* ============ 工具 ============ */

const storageKey = (s: Subject) => `errors_${s}`;

const readErrors = (s: Subject): ErrorItem[] => {
  try {
    const raw = localStorage.getItem(storageKey(s));
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
};

const writeErrors = (s: Subject, list: ErrorItem[]) => {
  localStorage.setItem(storageKey(s), JSON.stringify(list));
};

const genId = () => `err_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

/** 相对时间：X 秒前 / X 分钟前 / X 小时前 / X 天前 */
function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return `${Math.max(1, Math.floor(diff / 1000))} 秒前`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return `${Math.floor(diff / 86_400_000)} 天前`;
}

/* ============ 组件 ============ */

interface ErrorBookProps {
  /** 由 antd App 注入 */
  messageApi: ReturnType<typeof message.useMessage>[0];
}

function ErrorBookInner({ messageApi }: ErrorBookProps) {
  const [subject, setSubject] = useState<Subject>('math');
  const [formOpen, setFormOpen] = useState(false);
  const [list, setList] = useState<ErrorItem[]>([]);
  const [form] = Form.useForm<{
    questionText: string;
    reason: ErrorReason;
    knowledgeNames: string[];
    keyword: string;
  }>();

  // 关键词匹配状态
  const [matchResult, setMatchResult] = useState<KnowledgeEntry | null>(null);
  const [matchTried, setMatchTried] = useState(false);

  // 卡片展开状态
  const [summaryById, setSummaryById] = useState<Record<string, { loading: boolean; data?: KnowledgeSummaryResponse; error?: string }>>({});
  const [parseById, setParseById] = useState<Record<string, { loading: boolean; data?: ErrorParseResponse; error?: string }>>({});

  // 切学科时重读 localStorage
  useEffect(() => {
    setList(readErrors(subject));
    setMatchResult(null);
    setMatchTried(false);
  }, [subject]);

  const isEmpty = list.length === 0;

  /* ----- 录入 ----- */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const item: ErrorItem = {
        id: genId(),
        questionText: values.questionText.trim(),
        reason: values.reason,
        knowledgeNames: values.knowledgeNames ?? [],
        createdAt: Date.now(),
      };
      const next = [item, ...list];
      setList(next);
      writeErrors(subject, next);
      form.resetFields();
      setMatchResult(null);
      setMatchTried(false);
      setFormOpen(false);
      messageApi.success('错题已保存');
    } catch {
      // antd 校验失败会自动展示红字
    }
  };

  /* ----- 关键词匹配 ----- */
  const handleMatch = () => {
    const keyword: string = form.getFieldValue('keyword') ?? '';
    const found = matchKnowledge(keyword);
    setMatchTried(true);
    setMatchResult(found);
    if (found) {
      // 命中 → 自动预填入关联知识点（用户可改）
      const current: string[] = form.getFieldValue('knowledgeNames') ?? [];
      if (!current.includes(found.name)) {
        form.setFieldValue('knowledgeNames', [found.name, ...current]);
      }
    }
  };

  const confirmMatch = () => {
    if (!matchResult) return;
    const current: string[] = form.getFieldValue('knowledgeNames') ?? [];
    if (!current.includes(matchResult.name)) {
      form.setFieldValue('knowledgeNames', [matchResult.name, ...current]);
    }
    messageApi.success(`已关联：${matchResult.name}`);
  };

  /* ----- 复盘 ----- */
  const handleSummary = async (item: ErrorItem) => {
    setSummaryById((m) => ({ ...m, [item.id]: { loading: true } }));
    try {
      const stats = (() => {
        const tally: Record<string, number> = {};
        list.forEach((e) => e.knowledgeNames.forEach((k) => (tally[k] = (tally[k] ?? 0) + 1)));
        const sorted = Object.entries(tally).sort((a, b) => b[1] - a[1]).slice(0, 3);
        return sorted.length
          ? sorted.map(([k, v]) => `${k}×${v}`).join('、')
          : '（暂无关联知识点数据）';
      })();
      const data = await generateKnowledgeSummary({
        subject: SUBJECT_TABS.find((t) => t.key === subject)?.label ?? subject,
        period: '本周',
        error_summary: `共 ${list.length} 道错题，集中在 ${stats}`,
        mastery_changes: '函数单调性 65%，数列求和 55%',
        state_context: '本周学习状态平稳',
      });
      setSummaryById((m) => ({ ...m, [item.id]: { loading: false, data } }));
    } catch {
      setSummaryById((m) => ({ ...m, [item.id]: { loading: false, error: 'failed' } }));
      messageApi.error('复盘生成失败，请稍后再试');
    }
  };

  /* ----- AI 解析 ----- */
  const handleParse = async (item: ErrorItem) => {
    setParseById((m) => ({ ...m, [item.id]: { loading: true } }));
    const matched = KNOWLEDGE_BASE.find((k) => item.knowledgeNames.includes(k.name));
    try {
      const data = await parseError({
        question_text: item.questionText,
        matched_knowledge: matched
          ? { name: matched.name, definition: matched.definition, error_tip: matched.errorTip }
          : undefined,
      });
      setParseById((m) => ({ ...m, [item.id]: { loading: false, data } }));
    } catch {
      setParseById((m) => ({ ...m, [item.id]: { loading: false, error: 'failed' } }));
      messageApi.error('解析生成失败，请稍后重试');
    }
  };

  /* ----- 渲染 ----- */
  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <div className="eb-header">
          <h1 className="page-title">
            错题本
            <span className="en">Error Book</span>
          </h1>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setFormOpen((v) => !v)}
            className="eb-toggle-btn"
          >
            {formOpen ? '收起录入' : '录入错题'}
          </Button>
        </div>

        <Tabs
          className="eb-tabs"
          activeKey={subject}
          onChange={(k) => setSubject(k as Subject)}
          items={SUBJECT_TABS.map((t) => ({ key: t.key, label: t.label }))}
        />

        <Collapse
          activeKey={formOpen ? ['form'] : []}
          bordered={false}
          ghost
          className="eb-form-collapse"
          items={[
            {
              key: 'form',
              label: <span className="eb-form-label">录入新错题</span>,
              showArrow: false,
              children: (
                <Form
                  form={form}
                  layout="vertical"
                  className="eb-form glass"
                  initialValues={{ reason: 'concept', knowledgeNames: [] }}
                >
                  {/* 关键词匹配行（搜题） */}
                  <div className="eb-row-2">
                    <Form.Item label="题目关键词" name="keyword" className="eb-flex-1">
                      <Input placeholder="输入题目关键词，如：复合函数求值域" />
                    </Form.Item>
                    <Form.Item label=" " className="eb-flex-0">
                      <Button icon={<BulbOutlined />} onClick={handleMatch}>
                        匹配知识点
                      </Button>
                    </Form.Item>
                  </div>

                  {matchTried && matchResult && (
                    <div className="eb-match-card glass">
                      <div className="eb-match-head">
                        <span
                          className="eb-match-dot"
                          style={{ background: matchResult.mastery < 0.4 ? 'var(--danger-soft)' : matchResult.mastery <= 0.7 ? 'var(--warning)' : 'var(--success)' }}
                        />
                        <span className="eb-match-name">{matchResult.name}</span>
                        <span className="eb-match-pct">
                          {Math.round(matchResult.mastery * 100)}%
                        </span>
                      </div>
                      <div className="eb-match-def">{matchResult.definition}</div>
                      <div className="eb-match-tip">
                        <span aria-hidden>⚠</span>
                        {matchResult.errorTip}
                      </div>
                      <Button size="small" type="primary" onClick={confirmMatch}>
                        确认关联此知识点
                      </Button>
                    </div>
                  )}

                  {matchTried && !matchResult && (
                    <div className="eb-match-empty">
                      未匹配到知识点，请手动选择
                      <div className="eb-match-fallback">
                        {KNOWLEDGE_BASE.map((k) => (
                          <Tag
                            key={k.name}
                            className="eb-fallback-tag"
                            onClick={() => {
                              const current: string[] = form.getFieldValue('knowledgeNames') ?? [];
                              if (!current.includes(k.name)) {
                                form.setFieldValue('knowledgeNames', [k.name, ...current]);
                              }
                            }}
                          >
                            {k.name}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}

                  <Form.Item
                    label="题目原文"
                    name="questionText"
                    rules={[{ required: true, message: '请输入题目原文' }]}
                  >
                    <Input.TextArea
                      placeholder="粘贴错题原文…"
                      autoSize={{ minRows: 3, maxRows: 6 }}
                    />
                  </Form.Item>

                  <div className="eb-row-2">
                    <Form.Item
                      label="我的错因"
                      name="reason"
                      rules={[{ required: true, message: '请选择错因' }]}
                      className="eb-flex-1"
                    >
                      <Select options={REASON_OPTIONS} placeholder="选择错因" />
                    </Form.Item>
                    <Form.Item
                      label="关联知识点"
                      name="knowledgeNames"
                      className="eb-flex-1"
                    >
                      <Select
                        mode="multiple"
                        allowClear
                        placeholder="可多选"
                        options={SUBJECT_KNOWLEDGE[subject].map((k) => ({ value: k, label: k }))}
                      />
                    </Form.Item>
                  </div>

                  <div className="eb-form-actions">
                    <Button onClick={() => { form.resetFields(); setMatchResult(null); setMatchTried(false); }}>
                      清空
                    </Button>
                    <Button type="primary" onClick={handleSubmit}>
                      保存错题
                    </Button>
                  </div>
                </Form>
              ),
            },
          ]}
        />

        {isEmpty ? (
          <div className="eb-empty glass">
            <div className="eb-empty-icon" aria-hidden>
              <FileTextOutlined />
            </div>
            <p className="eb-empty-text">还没有错题记录，学完记得来这里记录哦 📝</p>
            <Button type="primary" onClick={() => setFormOpen(true)}>
              去录入第一道错题
            </Button>
          </div>
        ) : (
          <div className="eb-list">
            {list.map((item) => {
              const tone = REASON_TONE[item.reason];
              const summary = summaryById[item.id];
              const parsed = parseById[item.id];
              return (
                <article key={item.id} className="eb-card glass">
                  <p className="eb-card-question">{item.questionText}</p>
                  <div className="eb-card-meta">
                    <span
                      className="eb-reason-tag"
                      style={{ background: tone.bg, borderColor: tone.border, color: tone.color }}
                    >
                      {REASON_LABEL[item.reason]}
                    </span>
                    {item.knowledgeNames.map((k) => (
                      <span key={k} className="eb-kp-tag">
                        {k}
                      </span>
                    ))}
                    <span className="eb-card-time">{relativeTime(item.createdAt)}</span>
                  </div>
                  <div className="eb-card-actions">
                    <Button
                      loading={summary?.loading}
                      onClick={() => handleSummary(item)}
                      icon={<BulbOutlined />}
                    >
                      生成复盘
                    </Button>
                    <Button
                      loading={parsed?.loading}
                      onClick={() => handleParse(item)}
                      icon={<RobotOutlined />}
                    >
                      AI 解析
                    </Button>
                  </div>

                  {summary?.data && (
                    <div className="eb-summary">
                      <div className="eb-summary-label">本周复盘</div>
                      <p className="eb-summary-text">{summary.data.summary}</p>
                    </div>
                  )}
                  {summary?.loading && !summary.data && (
                    <Skeleton active paragraph={{ rows: 2 }} className="eb-skel" />
                  )}

                  {parsed?.data && (
                    <div className="eb-parse">
                      <div className="eb-parse-label">AI 解析</div>
                      <p className="eb-parse-text">{parsed.data.explanation}</p>
                      {parsed.data.steps && parsed.data.steps.length > 0 && (
                        <ol className="eb-parse-steps">
                          {parsed.data.steps.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ol>
                      )}
                      {parsed.data.review_suggestion && (
                        <div className="eb-parse-review">
                          复习建议：{parsed.data.review_suggestion}
                        </div>
                      )}
                    </div>
                  )}
                  {parsed?.loading && !parsed.data && (
                    <Skeleton active paragraph={{ rows: 2 }} className="eb-skel" />
                  )}
                </article>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}

export default function ErrorBook() {
  // 在 antd App 包裹下提供 message 上下文
  const [messageApi, contextHolder] = message.useMessage();
  return (
    <AntdApp>
      {contextHolder}
      <ErrorBookInner messageApi={messageApi} />
    </AntdApp>
  );
}

/**
 * 学科知识浏览页 · 板块二演示
 *
 * 布局：左 30% 知识点树 / 右 70% 详情
 * 数据：硬编码（PRD 12.2 选型决策后才会接真实知识库）
 */

import { useMemo, useState } from 'react';
import { Modal, Tree, theme as antdTheme } from 'antd';
import type { DataNode } from 'antd/es/tree';
import './index.css';

interface KnowledgeNode {
  /** 显示名 */
  label: string;
  /** 掌握度 0-1 */
  mastery: number;
  /** 一句话定义 */
  definition: string;
  /** 易错点 */
  errorTip: string;
}

/** 硬编码知识点数据 · PRD 12.4 知识内容维度（演示用） */
const KNOWLEDGE_TREE: Record<string, KnowledgeNode[]> = {
  函数: [
    {
      label: '单调性',
      mastery: 0.65,
      definition: '复合函数单调性：同增异减原则——外层与内层单调性相同时，复合函数单调递增；相反时递减。',
      errorTip: '注意内层函数的值域是否在外层函数的定义域内',
    },
    {
      label: '奇偶性',
      mastery: 0.8,
      definition: '若 f(-x) = f(x) 为偶函数，f(-x) = -f(x) 为奇函数；定义域需关于原点对称。',
      errorTip: '判断奇偶性前先检查定义域是否对称',
    },
    {
      label: '复合函数',
      mastery: 0.45,
      definition: '由 y = f(g(x)) 形式嵌套构成；单调性遵循"同增异减"，值域由内向外逐层求解。',
      errorTip: '注意内层函数的值域是否在外层函数定义域内',
    },
  ],
  几何: [
    {
      label: '三角形',
      mastery: 0.85,
      definition: '三边构成的平面图形；常用正弦定理 a/sinA = b/sinB = c/sinC 与余弦定理 a² = b² + c² - 2bc·cosA。',
      errorTip: '余弦定理注意多解情况（钝角 / 锐角三角形）',
    },
    {
      label: '圆',
      mastery: 0.7,
      definition: '到定点（圆心）距离等于定长（半径）的点的集合；切线垂直于过切点的半径。',
      errorTip: '切线垂直于过切点的半径，弦的中垂线过圆心',
    },
  ],
  数列: [
    {
      label: '等差数列',
      mastery: 0.6,
      definition: '相邻两项差相等的数列；通项 an = a1 + (n-1)d，前 n 项和 Sn = n(a1+an)/2。',
      errorTip: '通项公式与前 n 项和公式别混用',
    },
    {
      label: '等比数列',
      mastery: 0.55,
      definition: '相邻两项比值相等的数列；通项 an = a1·q^(n-1)，前 n 项和 Sn = a1(1-q^n)/(1-q)。',
      errorTip: 'q=1 时求和公式不适用，需用 Sn = n·a1 单独处理',
    },
  ],
};

/** 掌握度按阈值映射：<40 红 / 40-70 橙 / >70 绿（取自 antd 主题 token，保证与全局一致） */
function useMasteryTone() {
  const { token } = antdTheme.useToken();
  return (mastery: number): string => {
    if (mastery < 0.4) return token.colorError;
    if (mastery <= 0.7) return token.colorWarning;
    return token.colorSuccess;
  };
}

export default function Knowledge() {
  const [selected, setSelected] = useState<KnowledgeNode>(() => KNOWLEDGE_TREE.函数[0]);
  const [graphOpen, setGraphOpen] = useState(false);
  const masteryTone = useMasteryTone();

  /** 树形数据：根节点为学科，下面挂分类与叶子 */
  const treeData: DataNode[] = useMemo(
    () => [
      {
        title: '数学',
        key: 'math',
        selectable: false,
        children: Object.entries(KNOWLEDGE_TREE).map(([category, nodes]) => ({
          title: category,
          key: `math-${category}`,
          selectable: false,
          children: nodes.map((n) => {
            const dataNode: DataNode = {
              title: (
                <span className="kb-tree-leaf">
                  <span className="kb-tree-dot" style={{ background: masteryTone(n.mastery) }} />
                  <span className="kb-tree-label">{n.label}</span>
                  <span
                    className="kb-tree-pct"
                    style={{ color: masteryTone(n.mastery) }}
                  >
                    {Math.round(n.mastery * 100)}%
                  </span>
                </span>
              ),
              key: `math-${category}-${n.label}`,
              isLeaf: true,
              selectable: true,
            };
            // 自定义数据挂在 DataNode 上，onSelect 中通过 info.node.__node 取出
            (dataNode as DataNode & { __node: KnowledgeNode }).__node = n;
            return dataNode;
          }),
        })),
      },
    ],
    [],
  );

  const onSelect = (keys: React.Key[], info: { node: DataNode }) => {
    if (!keys.length) return;
    const node: KnowledgeNode | undefined = (info.node as unknown as { __node?: KnowledgeNode }).__node;
    if (node) setSelected(node);
  };

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          学科知识库
          <span className="en">Knowledge Base</span>
        </h1>

        <div className="kb-layout">
          <aside className="kb-tree glass">
            <div className="kb-tree-header">数学 · 知识点</div>
            <Tree
              defaultExpandedKeys={['math', 'math-函数', 'math-几何', 'math-数列']}
              defaultSelectedKeys={['math-函数-单调性']}
              onSelect={onSelect}
              treeData={treeData}
              blockNode
            />
          </aside>

          <section className="kb-detail glass">
            <header className="kb-detail-header">
              <h2 className="kb-detail-title">{selected.label}</h2>
              <span
                className="kb-detail-mastery"
                style={{ color: masteryTone(selected.mastery) }}
              >
                掌握度 {Math.round(selected.mastery * 100)}%
              </span>
            </header>

            <div className="kb-detail-block">
              <div className="kb-detail-label">定义</div>
              <p className="kb-detail-text">{selected.definition}</p>
            </div>

            <div className="kb-detail-block">
              <div className="kb-detail-label">易错点</div>
              <p className="kb-detail-error">
                <span className="kb-detail-error-icon" aria-hidden>⚠</span>
                {selected.errorTip}
              </p>
            </div>

            <div className="kb-detail-block">
              <div className="kb-detail-label">关联题</div>
              <p className="kb-detail-faint">暂无数据，录入错题后自动关联</p>
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
          </section>
        </div>

        <Modal
          open={graphOpen}
          title="概念图谱"
          onCancel={() => setGraphOpen(false)}
          onOk={() => setGraphOpen(false)}
          okText="知道了"
          cancelButtonProps={{ style: { display: 'none' } }}
        >
          <p>图谱功能将在 v2.3 上线。</p>
        </Modal>
      </main>
    </>
  );
}

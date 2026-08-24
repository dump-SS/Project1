/**
 * 学科概念图谱（板块二 v2.3）
 *
 * 选型：vis-network（ADR docs/adr-graph-visualization.md）。
 * 数据源：GET /knowledge/subjects/{code}/graph（后端 v2.1 树形占位，v2.3 关系边）。
 * 节点色阶 = mastery（红<0.4 / 橙0.4-0.7 / 绿>0.7），点击节点联动选中知识点。
 */
import { useEffect, useRef, useState } from 'react';
import { DataSet, Network } from 'vis-network/standalone';
import { fetchKnowledgeGraph } from '@/services/knowledgeV2';
import { fetchSubjectMastery } from '@/services/mastery';
import type { KnowledgePoint } from '@/services/knowledgeV2';

interface Props {
  subjectCode: string;
  onSelect?: (point: KnowledgePoint) => void;
}

function tone(v: number | null | undefined): string {
  if (v === null || v === undefined) return '#c0c0c0';
  if (v < 0.4) return '#cf1322';
  if (v <= 0.7) return '#d48806';
  return '#389e0d';
}

export default function KnowledgeGraphView({ subjectCode, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState<KnowledgePoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [graph, mastery] = await Promise.all([
          fetchKnowledgeGraph(subjectCode),
          fetchSubjectMastery(subjectCode).catch(() => null),
        ]);
        if (cancelled) return;
        // 掌握度映射（pointId → mastery）
        const mm: Record<string, number> = {};
        for (const p of mastery?.points ?? []) {
          if (p.mastery !== null) mm[p.pointId] = p.mastery;
        }
        // 把 mastery 混进 point（挂在 definition 前的临时字段不可行，用本地映射）
        setPoints(graph.nodes);
        setMasteryMap(mm);
        setEdges(
          graph.edges.map((e) => ({
            from: e.srcPointId,
            to: e.dstPointId,
          })),
        );
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '图谱加载失败');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subjectCode]);

  const [masteryMap, setMasteryMap] = useState<Record<string, number>>({});
  const [edges, setEdges] = useState<Array<{ from: string; to: string }>>([]);
  const networkRef = useRef<Network | null>(null);

  useEffect(() => {
    if (!containerRef.current || points.length === 0) return;
    const nodes = new DataSet(
      points.map((p) => ({
        id: p.pointId,
        label: p.name,
        color: { background: tone(masteryMap[p.pointId]), border: '#fff' },
        title: `<b>${p.name}</b><br/>${p.definition ?? ''}`,
      })),
    );
    const network = new Network(
      containerRef.current,
      {
        nodes,
        edges: new DataSet(edges.map((e, i) => ({ id: `e${i}`, ...e }))),
      },
      {
      physics: { solver: 'barnesHut', stabilization: { iterations: 120 } },
      nodes: { shape: 'dot', size: 18, font: { size: 13 } },
      interaction: { hover: true },
    });
    networkRef.current = network;
    network.on('click', (params) => {
      const id = params.nodes?.[0];
      if (!id || !onSelect) return;
      const p = points.find((x) => x.pointId === id);
      if (p) onSelect(p);
    });
    return () => {
      network.destroy();
      networkRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, edges, masteryMap]);

  if (error) return <p style={{ color: '#999', padding: 16 }}>{error}</p>;
  if (points.length === 0) return <p style={{ color: '#999', padding: 16 }}>加载图谱中…</p>;
  return <div ref={containerRef} style={{ width: '100%', height: 420 }} />;
}

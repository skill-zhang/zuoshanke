/** ActionMapView — React Flow 行动图渲染组件 */
import { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  NodeProps,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import type { ActionNode as ActionNodeData, ActionEdge as ActionEdgeData } from '../api/client';

// ═══ dagre 自动布局 ═══
function getLayoutedElements(
  nodes: ActionNodeData[],
  edges: ActionEdgeData[],
  nodeStatusOverrides?: Record<string, string>,
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'TB',
    align: 'UL',
    nodesep: 100,
    ranksep: 100,
    edgesep: 30,
    marginx: 60,
    marginy: 50,
  });

  nodes.forEach((n) => {
    const width = Math.max(n.label.length * 14 + 50, 120);
    const height = n.type === 'decision' ? 64 : (n.status === 'failed' || n.status === 'failed_verify' ? 56 : 46);
    g.setNode(n.id, { width, height });
  });

  edges.forEach((e) => {
    g.setEdge(e.from_node_id, e.to_node_id);
  });

  dagre.layout(g);

  // ═══ 按层居中（不改 dagre，直接在 rfNodes 应用偏移） ═══
  const nodePositions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n) => {
    const pos = g.node(n.id);
    nodePositions[n.id] = { x: pos.x, y: pos.y };
  });

  // 按 y 差值分组 (>40px 算新层)
  const sorted = nodes
    .map((n) => ({ id: n.id, y: nodePositions[n.id].y }))
    .sort((a, b) => a.y - b.y);
  const ranks: string[][] = [];
  let curRank: string[] = [sorted[0].id];
  let lastY = sorted[0].y;
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].y - lastY > 40) {
      ranks.push(curRank);
      curRank = [sorted[i].id];
    } else {
      curRank.push(sorted[i].id);
    }
    lastY = sorted[i].y;
  }
  ranks.push(curRank);

  // 算每层偏移量
  const CENTER = 500;
  const offsets: Record<string, number> = {};
  ranks.forEach((nodeIds) => {
    if (nodeIds.length === 0) return;
    const xs = nodeIds.map((id) => nodePositions[id].x);
    const groupCenter = (Math.min(...xs) + Math.max(...xs)) / 2;
    const offset = CENTER - groupCenter;
    nodeIds.forEach((id) => { offsets[id] = offset; });
  });

  // 智能 Handle + rfNodes
  const rfNodes: Node[] = nodes.map((n) => {
    const pos = nodePositions[n.id];
    const ox = offsets[n.id] || 0;
    return {
      id: n.id,
      type: 'actionNode',
      position: { x: pos.x + ox - (g.node(n.id).width || 120) / 2, y: pos.y - (g.node(n.id).height || 46) / 2 },
      data: {
        label: n.label,
        nodeType: n.type,
        nodeStatus: (nodeStatusOverrides && nodeStatusOverrides[n.id]) || n.status,
        origin: n.origin,
        subLabel: (nodeStatusOverrides && nodeStatusOverrides[n.id] === 'running')
          ? '⏳ 执行中'
          : (n.status === 'failed' || n.status === 'failed_verify'
            ? (n.verification?.checks?.find((c: any) => !c.passed)?.target?.slice(0, 25) || '验证失败')
            : (n.status === 'running' ? '⏳ 执行中' : undefined)),
      },
    };
  });


  const rfEdges: Edge[] = edges.map((e) => {
    const src = g.node(e.from_node_id);
    const tgt = g.node(e.to_node_id);
    // 判断是否垂直直连：源在上、目标在下，且 x 接近
    const isVertical = src && tgt && (
      tgt.y > src.y + 30 && Math.abs(tgt.x - src.x) < src.width * 1.5
    );

    let sourceHandle: string;
    let targetHandle: string;

    if (isVertical) {
      sourceHandle = 'bottom';
      targetHandle = 'top';
    } else if (src && tgt && tgt.x > src.x) {
      // 目标在右边 → 从右边出，进左边
      sourceHandle = 'right-src';
      targetHandle = 'left';
    } else {
      // 目标在左边或默认
      sourceHandle = 'left-src';
      targetHandle = 'right';
    }

    return {
      id: e.id,
      source: e.from_node_id,
      target: e.to_node_id,
      sourceHandle,
      targetHandle,
      label: e.label,
      type: 'default',
      animated: e.type === 'fallback',
      style: {
        stroke: e.type === 'fallback' ? '#d29922' : '#6e7681',
        strokeDasharray: e.type === 'fallback' ? '5,3' : undefined,
        strokeWidth: 1.5,
      },
      labelStyle: { fill: '#8b949e', fontSize: 10, fontWeight: 400 },
      labelBgStyle: { fill: '#161b22', fillOpacity: 0.9 },
      labelBgPadding: [4, 3] as [number, number],
      labelBgBorderRadius: 3,
    };
  });

  return { nodes: rfNodes, edges: rfEdges };
}

// ═══ 状态 → 颜色映射 ═══
const STATUS_STYLE: Record<string, { bg: string; border: string; text: string }> = {
  completed:        { bg: 'rgba(63,185,80,0.12)',  border: '#3fb950', text: '#c9d1d9' },
  failed:           { bg: 'rgba(248,81,73,0.1)',   border: '#f85149', text: '#c9d1d9' },
  failed_verify:    { bg: 'rgba(248,81,73,0.1)',   border: '#f85149', text: '#c9d1d9' },
  timeout:          { bg: 'rgba(210,153,34,0.1)',  border: '#d29922', text: '#c9d1d9' },
  running:          { bg: 'rgba(88,166,255,0.12)', border: '#58a6ff', text: '#e6edf3' },
  verifying:        { bg: 'rgba(88,166,255,0.08)', border: '#58a6ff', text: '#e6edf3' },
  verified:         { bg: 'rgba(88,166,255,0.08)', border: '#58a6ff', text: '#e6edf3' },
  retrying:         { bg: 'rgba(210,153,34,0.08)', border: '#d29922', text: '#e6edf3' },
  awaiting_approval:{ bg: 'rgba(188,140,255,0.1)', border: '#bc8cff', text: '#e6edf3' },
  pending:          { bg: 'rgba(110,118,129,0.06)',border: '#6e7681', text: '#b0b8c0' },
};

const TYPE_STYLE: Record<string, { bg: string; border: string; text: string; borderRadius: string }> = {
  start:     { bg: 'rgba(188,140,255,0.06)', border: '#bc8cff', text: '#c9d1d9', borderRadius: '12px' },
  decision:  { bg: 'rgba(248,81,73,0.06)',   border: '#f85149', text: '#c9d1d9', borderRadius: '10px' },
  milestone: { bg: 'rgba(63,185,80,0.06)',   border: '#3fb950', text: '#c9d1d9', borderRadius: '12px' },
  end:       { bg: 'rgba(188,140,255,0.06)', border: '#bc8cff', text: '#c9d1d9', borderRadius: '12px' },
  exec:      { bg: 'rgba(88,166,255,0.04)',  border: '#58a6ff', text: '#c9d1d9', borderRadius: '10px' },
};

// ═══ 自定义节点 ═══
function ActionMapNode({ data }: NodeProps) {
  const nodeData = data as any;
  const type = nodeData.nodeType || 'exec';
  const status = nodeData.nodeStatus || 'pending';

  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  const t = TYPE_STYLE[type] || TYPE_STYLE.exec;

  const isFallback = nodeData.origin && nodeData.origin !== 'original';
  const borderStyle = isFallback ? '4,3' : 'solid';
  const borderColor = isFallback ? '#d29922' : (s.border || t.border);

  return (
    <div style={{
      background: s.bg || t.bg,
      border: `1.5px solid ${borderColor}`,
      borderStyle: isFallback ? 'dashed' : 'solid',
      borderRadius: t.borderRadius,
      padding: '8px 14px',
      fontSize: '12px',
      color: s.text || t.text,
      minWidth: '80px',
      textAlign: 'center',
      position: 'relative',
    }}>
      <Handle type="target" position={Position.Top} id="top" style={{ background: '#6e7681', width: 6, height: 6 }} />
      <Handle type="target" position={Position.Left} id="left" style={{ background: '#6e7681', width: 6, height: 6 }} />
      <Handle type="target" position={Position.Right} id="right" style={{ background: '#6e7681', width: 6, height: 6 }} />
      <div style={{ fontWeight: type === 'start' || type === 'end' ? 600 : 400 }}>
        {nodeData.label}
      </div>
      {nodeData.subLabel && (
        <div style={{ fontSize: '10px', color: '#8b949e', marginTop: 2 }}>
          {nodeData.subLabel}
        </div>
      )}
      {isFallback && (
        <div style={{
          position: 'absolute', top: -8, right: -6,
          background: '#d29922', color: '#0d1117',
          fontSize: '9px', padding: '1px 5px', borderRadius: '8px',
          fontWeight: 600,
        }}>
          备选
        </div>
      )}
      <Handle type="source" position={Position.Bottom} id="bottom" style={{ background: '#6e7681', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Left} id="left-src" style={{ background: '#6e7681', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} id="right-src" style={{ background: '#6e7681', width: 6, height: 6 }} />
    </div>
  );
}

const nodeTypes = { actionNode: ActionMapNode };

// ═══ Props ═══
interface Props {
  nodes: ActionNodeData[];
  edges: ActionEdgeData[];
  nodeStatusOverrides?: Record<string, string>;
}

export default function ActionMapView({ nodes: actionNodes, edges: actionEdges, nodeStatusOverrides }: Props) {
  const { nodes: rfNodes, edges: rfEdges } = useMemo(
    () => getLayoutedElements(actionNodes, actionEdges, nodeStatusOverrides),
    [actionNodes, actionEdges, nodeStatusOverrides]
  );

  const onInit = useCallback((instance: any) => {
    setTimeout(() => instance.fitView({ padding: 0.2, duration: 300 }), 100);
  }, []);

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      onInit={onInit}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      proOptions={{ hideAttribution: true }}
      style={{ background: '#0d1117' }}
    >
      <Background color="#21262d" gap={20} />
      <Controls style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '6px' }} />
      <MiniMap
        style={{ background: '#161b22', border: '1px solid #30363d' }}
        nodeColor={(n) => {
          const s = STATUS_STYLE[(n.data as any)?.nodeStatus] || STATUS_STYLE.pending;
          return s.border;
        }}
        maskColor="rgba(13,17,23,0.7)"
      />
    </ReactFlow>
  );
}

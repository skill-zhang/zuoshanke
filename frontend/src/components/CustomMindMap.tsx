/**
 * CustomMindMap — 基于 d3-hierarchy 的自定义 SVG 思维导图渲染器
 *
 * 替换 markmap 渲染，支持：
 * - 节点状态颜色（已收敛/已废弃/反馈注入/头脑风暴/已确认）
 * - 收敛合并标注（SVG 外部 React 列表）
 * - d3-zoom 缩放平移
 * - 初始 fit 全图
 *
 * 接口：接收扁平 ThinkNode[] + MergeRecord[]，组件内用 d3.stratify() 建树
 *
 * 使用方式：
 *   import { CustomMindMap, CustomMindMapDemo } from './CustomMindMap';
 *
 *   <CustomMindMap nodes={nodes} merges={merges} onNodeClick={id => ...} />
 *
 * 本地预览（不依赖任何后端）：
 *   在任意 React 页面中 <CustomMindMapDemo /> 即可
 */

import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

// ═══════════════════════════════════════════════════════════════════
//  公开类型
// ═══════════════════════════════════════════════════════════════════

export interface ThinkNodeData {
  id: string;
  parent_id: string | null;
  label: string;
  status: string; // 'refined' | 'created' | 'discarded' | 'confirmed' | 扩展
  created_by?: string; // 'brainstorm' | 'reflect' | 'manual'
  action_status?: string | null; // 'in_queue' | null
  converged_from?: string[];
}

export interface MergeRecord {
  target_node_id: string;
  source_labels: string[];
}

export interface CustomMindMapProps {
  /** 扁平节点列表，组件内用 parent_id 建树 */
  nodes: ThinkNodeData[];
  /** 收敛合并记录（可选） */
  merges?: MergeRecord[];
  /** 点击节点回调 */
  onNodeClick?: (nodeId: string) => void;
  /** SVG 宽度（默认自适应容器） */
  width?: number;
  /** SVG 高度（默认 400） */
  height?: number;
  /** 额外 CSS class */
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════
//  节点样式映射表（写死，不开放给调用方）
// ═══════════════════════════════════════════════════════════════════

interface NodeStyle {
  nodeFill: string;       // rect 背景色
  stroke: string;         // 边框色
  strokeWidth: number;
  strokeDasharray?: string;
  textFill: string;       // 文字色
  prefix: string;         // 文字前缀 emoji
  labelOpacity: number;   // 透明度（废弃节点用）
  textDecoration?: string;
}

/** 按优先级排序的样式匹配规则 */
const STYLE_RULES: Array<{
  match: (n: ThinkNodeData) => boolean;
  style: NodeStyle;
}> = [
  // 1. 已废弃 — 灰色虚线 + 删除线 + 半透明
  {
    match: n => n.status === 'discarded',
    style: {
      nodeFill: 'rgba(100,100,120,0.05)',
      stroke: '#555',
      strokeWidth: 0.5,
      strokeDasharray: '3,2',
      textFill: '#666',
      prefix: '',
      labelOpacity: 0.5,
      textDecoration: 'line-through',
    },
  },
  // 2. 反馈注入 — 粉色虚线边框 + 💡
  {
    match: n => n.created_by === 'reflect',
    style: {
      nodeFill: 'rgba(236,72,153,0.08)',
      stroke: '#ec4899',
      strokeWidth: 1.5,
      strokeDasharray: '4,3',
      textFill: '#f472b6',
      prefix: '💡 ',
      labelOpacity: 1,
    },
  },
  // 3. 已确认 — 绿色边框 + ✅
  {
    match: n => n.status === 'confirmed',
    style: {
      nodeFill: 'rgba(34,197,94,0.08)',
      stroke: '#22c55e',
      strokeWidth: 1.5,
      textFill: '#4ade80',
      prefix: '✅ ',
      labelOpacity: 1,
    },
  },
  // 4. 已收敛 + 已入队列 — 绿色实线 + ✅
  {
    match: n => n.status === 'refined' && n.action_status === 'in_queue',
    style: {
      nodeFill: 'rgba(34,197,94,0.08)',
      stroke: '#22c55e',
      strokeWidth: 1.5,
      textFill: '#4ade80',
      prefix: '✅ ',
      labelOpacity: 1,
    },
  },
  // 5. 已收敛（未入队列）— 橙色 + 🔀
  {
    match: n => n.status === 'refined',
    style: {
      nodeFill: 'rgba(249,115,22,0.08)',
      stroke: '#f97316',
      strokeWidth: 1.5,
      textFill: '#fb923c',
      prefix: '🔀 ',
      labelOpacity: 1,
    },
  },
  // 6. 默认（created / brainstorming）— 蓝色
  {
    match: n => true, // catch-all
    style: {
      nodeFill: '#1e1e2e',
      stroke: '#3b82f6',
      strokeWidth: 1.5,
      textFill: '#60a5fa',
      prefix: '💭 ',
      labelOpacity: 1,
    },
  },
];

function getNodeStyle(node: ThinkNodeData): NodeStyle {
  for (const rule of STYLE_RULES) {
    if (rule.match(node)) return rule.style;
  }
  // unreachable — catch-all exists
  return STYLE_RULES[STYLE_RULES.length - 1].style;
}

/** 连接线颜色取自子节点边框色 */
function getLinkColor(node: ThinkNodeData): string {
  return getNodeStyle(node).stroke;
}

/** 生成唯一 marker ID（连接线箭头） */
function markerId(color: string): string {
  return `arrow-${color.replace(/[^a-zA-Z0-9]/g, '')}`;
}

/** 估算文本宽度（中文字符 ~14px，ASCII ~7.5px） */
function estimateTextWidth(text: string): number {
  let w = 0;
  for (const ch of text) {
    w += ch.charCodeAt(0) > 127 ? 14 : 7.5;
  }
  return w;
}

/** 根据文本宽度 + 深度计算 rect 宽度（越深越窄） */
function calcRectWidth(label: string, depth: number = 0): number {
  const maxW = depth === 0 ? 220 : depth === 1 ? 160 : 100;
  const minW = depth === 0 ? 108 : depth === 1 ? 80 : 55;
  return Math.max(minW, Math.min(estimateTextWidth(label) + 28, maxW));
}

// 按层级的矩形高度
const ROOT_RECT_H = 40;
const DOMAIN_RECT_H = 32;
const LEAF_RECT_H = 26;
const RECT_RX = 8;

// ═══════════════════════════════════════════════════════════════════
//  主组件
// ═══════════════════════════════════════════════════════════════════

export function CustomMindMap({
  nodes,
  merges = [],
  onNodeClick,
  width: propWidth,
  height: propHeight = 400,
  className = '',
}: CustomMindMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const initTransformRef = useRef<d3.ZoomTransform | null>(null);

  const handleReset = () => {
    const svgEl = svgRef.current;
    if (svgEl && zoomRef.current && initTransformRef.current) {
      d3.select(svgEl).call(zoomRef.current.transform, initTransformRef.current);
    }
  };

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl || !nodes.length) return;

    const container = containerRef.current!;
    const svg = d3.select(svgEl);
    const width = propWidth || container.clientWidth || 800;
    const height = propHeight;

    // ── 清除 & 定义 markers ──
    svg.selectAll('*').remove();
    const defs = svg.append('defs');

    // ── 建树 ──
    const stratify = d3.stratify<ThinkNodeData>()
      .id(d => d.id)
      .parentId(d => {
        if (!d.parent_id) return null;
        // 父节点必须存在，否则 stratify 会抛错
        const parentExists = nodes.some(n => n.id === d.parent_id);
        return parentExists ? d.parent_id : null;
      });

    const root = stratify(nodes);

    // ── 树布局：自动计算间距 ──
    // 统计叶子数，估算合理水平间距防重叠
    const leafCount = root.leaves().length;
    const avgLabelWidth = nodes.reduce((s, n) => s + calcRectWidth(n.label, 1), 0) / nodes.length;
    const availW = container.clientWidth - 40;
    // 水平间距：让树总宽 ≈ availW × 1.2，但最小 30px（防重叠），最大 80px
    const sepfac = 2.0; // 同父 separation 因子
    const idealHSpacing = leafCount > 1 ? (availW * 1.2) / (leafCount * sepfac + 1) : 60;
    const SIBLING_H_SPACING = Math.max(Math.min(idealHSpacing, 80), Math.min(avgLabelWidth / sepfac, 30));
    const LEVEL_V_SPACING = 120; // 固定竖直间距
    const treeLayout = d3.tree<ThinkNodeData>()
      .nodeSize([SIBLING_H_SPACING, LEVEL_V_SPACING])
      .separation((a, b) => {
        // 同父间距小，异父稍大
        return a.parent === b.parent ? 2.0 : 2.5;
      });

    treeLayout(root);

    // ── 计算所有节点的 bounding box ──
    let bx = Infinity, bxMax = -Infinity, by = Infinity, byMax = -Infinity;
    root.each(d => {
      const rw = calcRectWidth(d.data.label, d.depth);
      const hw = rw / 2;
      const x = d.x || 0;
      const y = d.y || 0;
      const rectH = d.depth === 0 ? ROOT_RECT_H : d.depth === 1 ? DOMAIN_RECT_H : LEAF_RECT_H;
      bx = Math.min(bx, x - hw);
      bxMax = Math.max(bxMax, x + hw);
      by = Math.min(by, y);
      byMax = Math.max(byMax, y + rectH);
    });

    // 无节点 → 不渲染
    if (!isFinite(bx)) return;

    const pad = 32;
    const bw = bxMax - bx + pad * 2;
    const bh = byMax - by + pad * 2;
    const svgW = Math.max(width, bw);
    const svgH = Math.max(height, bh);

    svg
      .attr('viewBox', `0 0 ${svgW} ${svgH}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    // ── 背景 ──
    svg.append('rect')
      .attr('width', svgW)
      .attr('height', svgH)
      .attr('fill', '#16161e')
      .attr('rx', 8);

    // ── 缩放群组 ──
    const g = svg.append('g');

    // ── Zoom ──
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .filter(event => event.type !== 'dblclick')
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);
    zoomRef.current = zoom;

    // ── 初始 fit：让所有节点在视口中居中 ──
    {
      const contentW = bxMax - bx + 60;
      const contentH = byMax - by + 40;
      const scale = Math.min(svgW / contentW, svgH / contentH, 1.6);
      const tx = svgW / 2 - (bx + bxMax) * scale / 2;
      const ty = svgH / 2 - (by + byMax + ROOT_RECT_H) * scale / 2;
      const initTransform = d3.zoomIdentity.translate(tx, ty).scale(scale);
      initTransformRef.current = initTransform;
      svg.call(zoom.transform, initTransform);
    }

    // ── 绘制连接线 ──
    root.links().forEach(link => {
      const source = link.source as d3.HierarchyPointNode<ThinkNodeData>;
      const target = link.target as d3.HierarchyPointNode<ThinkNodeData>;
      const sx = source.x;
      const sourceRectH = source.depth === 0 ? ROOT_RECT_H : source.depth === 1 ? DOMAIN_RECT_H : LEAF_RECT_H;
      const sy = source.y + sourceRectH;
      const tx = target.x;
      const ty = target.y;

      const color = getLinkColor(target.data);
      const midY = (sy + ty) / 2;

      // 注册 marker
      const mId = markerId(color);
      if (!defs.select(`#${mId}`).size()) {
        defs.append('marker')
          .attr('id', mId)
          .attr('markerWidth', 6)
          .attr('markerHeight', 6)
          .attr('refX', 5)
          .attr('refY', 3)
          .attr('orient', 'auto')
          .append('path')
          .attr('d', 'M0,0 L6,3 L0,6')
          .attr('fill', color);
      }

      g.append('path')
        .attr('d', `M${sx},${sy} C${sx},${midY} ${tx},${midY} ${tx},${ty}`)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', 1.2)
        .attr('marker-end', `url(#${mId})`);
    });

    // ── 绘制节点 ──
    root.each(d => {
      const style = getNodeStyle(d.data);
      const rw = calcRectWidth(d.data.label, d.depth);
      const x = d.x!;
      const y = d.y!;

      const nodeG = g.append('g')
        .attr('cursor', onNodeClick ? 'pointer' : 'default')
        .on('click', (event: MouseEvent) => {
          event.stopPropagation();
          if (onNodeClick) onNodeClick(d.data.id);
        });

      // 按层级设定字号：根>一级>其他
      const fontSize = d.depth === 0 ? 18 : d.depth === 1 ? 14 : 11;
      const fontWeight = d.depth === 0 ? 700 : d.depth === 1 ? 600 : 400;
      const rectH = d.depth === 0 ? ROOT_RECT_H : d.depth === 1 ? DOMAIN_RECT_H : LEAF_RECT_H;

      // 矩形
      nodeG.append('rect')
        .attr('x', x - rw / 2)
        .attr('y', y)
        .attr('width', rw)
        .attr('height', rectH)
        .attr('rx', RECT_RX)
        .attr('fill', style.nodeFill)
        .attr('stroke', style.stroke)
        .attr('stroke-width', style.strokeWidth)
        .attr('stroke-dasharray', style.strokeDasharray || 'none')
        .attr('opacity', style.labelOpacity);

      // 文本（超出 16 字截断 + …）
      const displayText = `${style.prefix}${d.data.label}`;
      const truncated = displayText.length > 20
        ? displayText.slice(0, 18) + '…'
        : displayText;

      nodeG.append('text')
        .attr('x', x)
        .attr('y', y + rectH / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'central')
        .attr('fill', style.textFill)
        .attr('font-size', fontSize)
        .attr('font-weight', fontWeight)
        .attr('opacity', style.labelOpacity)
        .style('text-decoration', style.textDecoration || 'none')
        .style('user-select', 'none')
        .text(truncated);
    });

    // cleanup
    return () => {
      svg.on('.zoom', null);
    };
  }, [nodes, propWidth, propHeight, onNodeClick]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        width: '100%',
        height: propHeight,
        background: '#16161e',
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid #2a2a3a',
        position: 'relative',
      }}
    >
      <svg
        ref={svgRef}
        style={{ width: '100%', height: propHeight, display: 'block' }}
      />
      <button
        onClick={handleReset}
        title="复位"
        style={{
          position: 'absolute', top: 8, right: 8,
          width: 26, height: 26, borderRadius: 4,
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.1)',
          color: '#888', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, lineHeight: 1, padding: 0, zIndex: 10,
        }}
      >⟲</button>

      {/* ── 收敛合并标注（SVG 外部 React 列表） ── */}
      {merges.length > 0 && (
        <div style={{ padding: '8px 16px 14px', borderTop: '1px solid rgba(249,115,22,0.2)' }}>
          <div style={{ fontSize: 11, color: '#fb923c', fontWeight: 500, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🔀 收敛合并</span>
            <span style={{ fontSize: 10, color: '#666', fontWeight: 400 }}>{merges.length} 条记录</span>
          </div>
          {merges.map((merge, idx) => {
            const targetNode = nodes.find(n => n.id === merge.target_node_id);
            return (
              <div
                key={idx}
                style={{
                  fontSize: 11,
                  color: '#999',
                  marginBottom: 3,
                  cursor: onNodeClick ? 'pointer' : 'default',
                  padding: '3px 8px',
                  borderRadius: 4,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(249,115,22,0.08)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                onClick={() => onNodeClick?.(merge.target_node_id)}
              >
                <span style={{ color: '#fb923c' }}>🔀 </span>
                <span style={{ color: '#e0e0e8' }}>{targetNode?.label || merge.target_node_id}</span>
                <span style={{ color: '#666' }}> ← </span>
                {merge.source_labels.join(' + ')}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
//  Demo 组件（独立预览，不依赖任何后端或 store）
// ═══════════════════════════════════════════════════════════════════

const DEMO_NODES: ThinkNodeData[] = [
  // ── Root ──
  { id: 'root', parent_id: null, label: '天气推荐系统', status: 'confirmed', created_by: 'manual' },

  // ── Level 1 ──
  { id: 'data-layer', parent_id: 'root', label: '📦 数据层', status: 'created' },
  { id: 'algo-layer', parent_id: 'root', label: '⚙️ 算法层', status: 'created' },
  { id: 'display-layer', parent_id: 'root', label: '🖥️ 展示层', status: 'created' },

  // ── Level 2 — 数据层子节点 ──
  {
    id: 'weather-api', parent_id: 'data-layer', label: '调研天气API',
    status: 'refined', action_status: 'in_queue', created_by: 'brainstorm',
    converged_from: ['天气API选择', '免费天气接口', 'OpenWeather评估'],
  },
  {
    id: 'data-model', parent_id: 'data-layer', label: '设计数据模型',
    status: 'created', created_by: 'brainstorm',
  },
  {
    id: 'cache-layer', parent_id: 'data-layer', label: '缓存层设计',
    status: 'created', created_by: 'reflect',
  },

  // ── Level 2 — 算法层子节点 ──
  {
    id: 'recommend-algo', parent_id: 'algo-layer', label: '设计推荐算法',
    status: 'refined', action_status: 'in_queue', created_by: 'brainstorm',
  },
  {
    id: 'user-location', parent_id: 'algo-layer', label: '用户位置检测',
    status: 'created', created_by: 'brainstorm',
  },

  // ── Level 2 — 展示层子节点 ──
  {
    id: 'web-display', parent_id: 'display-layer', label: '搭建Web展示',
    status: 'refined', action_status: 'in_queue', created_by: 'brainstorm',
  },
  {
    id: 'multi-city', parent_id: 'display-layer', label: '多城市支持',
    status: 'created', created_by: 'brainstorm',
  },

  // ── 废弃节点 ──
  {
    id: 'crawler', parent_id: 'data-layer', label: '自建爬虫采集',
    status: 'discarded', created_by: 'brainstorm',
  },
  {
    id: 'paid-api', parent_id: 'data-layer', label: '付费API接入',
    status: 'discarded', created_by: 'brainstorm',
  },
];

const DEMO_MERGES: MergeRecord[] = [
  {
    target_node_id: 'weather-api',
    source_labels: ['天气API选择', '免费天气接口', 'OpenWeather评估'],
  },
  {
    target_node_id: 'recommend-algo',
    source_labels: ['协同过滤方案', '基于内容的推荐', '混合推荐评估'],
  },
  {
    target_node_id: 'web-display',
    source_labels: ['React版展示', '移动端适配'],
  },
];

export function CustomMindMapDemo() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 0', marginBottom: 8,
      }}>
        <span style={{ fontSize: 20 }}>🧠</span>
        <span style={{ fontSize: 16, fontWeight: 600, color: '#e0e0e8' }}>
          CustomMindMap Demo
        </span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 8,
          background: 'rgba(59,130,246,0.2)', color: '#60a5fa',
        }}>
          d3-hierarchy
        </span>
      </div>

      <CustomMindMap
        nodes={DEMO_NODES}
        merges={DEMO_MERGES}
        onNodeClick={id => console.log('[CustomMindMap] node click:', id)}
        height={420}
      />

      <div style={{
        marginTop: 12,
        display: 'flex', gap: 16, flexWrap: 'wrap',
        fontSize: 11, color: '#888',
      }}>
        <span><span style={{ color: '#3b82f6' }}>💭 蓝色</span> = 头脑风暴</span>
        <span><span style={{ color: '#22c55e' }}>✅ 绿色</span> = 已收敛 → 队列</span>
        <span><span style={{ color: '#f97316' }}>🔀 橙色</span> = 已收敛</span>
        <span><span style={{ color: '#ec4899' }}>💡 粉色虚线</span> = 反馈注入</span>
        <span><span style={{ color: '#666' }}>⬜ 灰色虚线</span> = 已废弃</span>
        <span>🔄 滚轮缩放 · 拖拽平移</span>
        <span>⏱️ {DEMO_NODES.length} 节点 · {DEMO_MERGES.length} 组合并</span>
      </div>
    </div>
  );
}

/** AgentLoopDashboard — 6 面板仪表盘
 *
 * 布局：
 *   ① 阶段循环图 (Loop Diagram)
 *   ② 可折叠思维导图 (Collapsible Mind Map)
 *   ③ 2×2 网格: TM收敛结果 / Priority Queue / Action Map / Reflect Timeline
 *   ④ Status Bar
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../stores/appStore';
import type { DashboardQueueItem, DashboardReflectItem, ThinkNode } from '../api/client';
import { CustomMindMap, type ThinkNodeData } from './CustomMindMap';

// ═══ 阶段循环图 ═══
const PHASES = [
  { key: 'diverge', icon: '🧠', label: '发散', desc: '头脑风暴\n拆解子问题' },
  { key: 'converge', icon: '🔀', label: '收敛', desc: '聚类去重\n合并相似项' },
  { key: 'sort', icon: '📊', label: '排序', desc: '依赖分析\n优先级队列' },
  { key: 'focus', icon: '🎯', label: '聚焦执行', desc: 'WIP 限制\n一次一件事' },
  { key: 'reflect', icon: '🔄', label: '反馈调整', desc: '结果反哺\n重新循环' },
];

function LoopDiagram() {
  const phase = useStore(s => s.dashboardPhase);
  const idx = PHASES.findIndex(p => p.key === phase);
  const currentScene = useStore(s => s.currentScene);
  const [showParams, setShowParams] = useState(false);
  const [threshold, setThreshold] = useState(currentScene?.converge_threshold ?? 2.0);
  const [rounds, setRounds] = useState(currentScene?.diverge_min_rounds ?? 2);
  const [enabled, setEnabled] = useState(currentScene?.converge_enabled ?? true);

  const saveParams = async () => {
    if (!currentScene) return;
    try {
      await fetch(`/api/scenes/${currentScene.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          converge_threshold: threshold,
          diverge_min_rounds: rounds,
          converge_enabled: enabled,
        }),
      });
      setShowParams(false);
    } catch (e) {
      console.error('保存参数失败', e);
    }
  };

  return (
    <div className="loop-diagram">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2>阶段循环</h2>
        <button
          className="param-btn"
          onClick={() => { setShowParams(v => !v); }}
          title="调整收敛参数"
          style={{
            background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
            color: '#a78bfa', padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
            fontSize: 12, display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          ⚙ 调整参数
        </button>
      </div>

      {showParams && (
        <div style={{
          background: '#1a1a2e', border: '1px solid #333', borderRadius: 8,
          padding: '14px 16px', marginBottom: 12,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#c084fc', marginBottom: 10 }}>收敛参数</div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
              发散建树轮数: <strong style={{ color: '#e6edf3' }}>{rounds}</strong>
            </div>
            <input type="range" min={1} max={10} step={1} value={rounds}
              onChange={e => setRounds(Number(e.target.value))}
              style={{ width: '100%', accentColor: '#a78bfa' }} />
          </div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
              收敛阈值: <strong style={{ color: '#e6edf3' }}>{threshold.toFixed(1)}×</strong>
            </div>
            <input type="range" min={1.0} max={5.0} step={0.1} value={threshold}
              onChange={e => setThreshold(Number(e.target.value))}
              style={{ width: '100%', accentColor: '#a78bfa' }} />
            <div style={{ fontSize: 10, color: '#484f58', display: 'flex', justifyContent: 'space-between' }}>
              <span>敏感 1.0</span><span>适中 2.0</span><span>谨慎 5.0</span>
            </div>
          </div>

          <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: '#8b949e' }}>自动收敛</span>
            <label style={{ position: 'relative', display: 'inline-block', width: 36, height: 20 }}>
              <input type="checkbox" checked={enabled}
                onChange={e => setEnabled(e.target.checked)}
                style={{ opacity: 0, width: 0, height: 0 }} />
              <span style={{
                position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                background: enabled ? '#a78bfa' : '#333', borderRadius: 10, transition: '.3s',
              }}>
                <span style={{
                  position: 'absolute', height: 16, width: 16, left: enabled ? 18 : 2, top: 2,
                  background: '#fff', borderRadius: '50%', transition: '.3s',
                }} />
              </span>
            </label>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowParams(false)}
              style={{ background: 'transparent', border: '1px solid #444', color: '#999', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
              取消
            </button>
            <button onClick={saveParams}
              style={{ background: '#7c3aed', border: 'none', color: '#fff', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
              保存
            </button>
          </div>
        </div>
      )}

      <div className="loop-flow">
        {PHASES.map((p, i) => (
          <span key={p.key} style={{ display: 'flex', alignItems: 'center' }}>
            <div className="loop-step">
              <div className={`icon ${p.key}`} style={{
                background: `rgba(139,92,246,0.2)`,
                border: i === idx ? `2px solid #a78bfa` : `2px solid rgba(139,92,246,0.4)`,
                opacity: 1,
              }}>
                {p.icon}
              </div>
              <div className="label" style={{ color: '#c084fc' }}>{p.label}</div>
              <div className="desc">{p.desc}</div>
            </div>
            {i < PHASES.length - 1 && (
              <div className="loop-arrow" style={{
                background: '#a78bfa',
                width: 56, height: 2, margin: '0 6px', flexShrink: 0,
                position: 'relative',
              }}>
                <span style={{
                  position: 'absolute', right: -4, top: -7,
                  color: '#a78bfa', fontSize: 15,
                }}>›</span>
              </div>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

// ═══ 思维导图（可收起 + 自适应高度） ═══
function CollapsibleMindMap() {
  const [expanded, setExpanded] = useState(true);
  const mmRef = useRef<HTMLDivElement>(null);
  const thinkingMap = useStore(s => s.thinkingMap);
  const nodesRef = useRef<any[]>([]);
  nodesRef.current = thinkingMap?.nodes || nodesRef.current;
  const nodes = nodesRef.current;

  const mindMapNodes = useMemo(() => {
    if (!nodes || nodes.length === 0) return [];
    return nodes.map((n: any) => ({
        id: n.id,
        parent_id: n.parent_id || null,
        label: n.label,
        status: n.status,
        created_by: n.created_by || 'brainstorm',
        action_status: n.action_status || null,
        converged_from: n.converged_from || [],
      }));
  }, [nodes]);

  return (
    <div className="dashboard-mindmap">
      <div className="mm-title-row" style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setExpanded(v => !v)}>
        <span className="collapse-arrow">{expanded ? '▼' : '▶'}</span>
        <h3>🧠 发散阶段 — Thinking Map 思维导图</h3>
        <span className="badge badge-blue">头脑风暴</span>
        <span className="badge badge-orange">收敛标记</span>
        <span className="badge badge-pink">反馈注入</span>
      </div>
      {expanded && (
        <>
          <div className="mm-legend">
            <span><span className="dot blue"></span> 活跃节点</span>
            <span><span className="dot green"></span> 已收敛→队列</span>
            <span><span className="dot orange"></span> 已收敛未分配</span>
            <span><span className="dot gray"></span> 头脑风暴中</span>
            <span><span className="dot pink"></span> 反馈新增</span>
            <span><span className="dot red"></span> 已废弃</span>
            <span className="mm-count">{nodes.length} 节点</span>
          </div>
          <div className="mm-body" ref={mmRef}>
            {nodes.length > 0 ? (
              <CustomMindMap nodes={mindMapNodes} />
            ) : (
              <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>
                发送消息后自动生成思维节点
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ═══ 场景标题映射 ═══
// 根据场景名关键词推断面板标题，不涉及 LLM，纯 UI 层
const SCENE_TITLE_MAP: [string[], string][] = [
  [['二手车', '买房', '购房', '购物', '装修', '招聘', '租房'], '注意事项'],
  [['软件', '需求', '项目', '规划', '开发', '功能', '迭代', '重构', 'feature'], '需求列表'],
  [['旅游', '出行', '旅行', '自驾', '路线', '攻略'], '行程清单'],
  [['学习', '研究', '调研', '论文', '阅读', '报告'], '学习要点'],
];

function guessPanelTitle(sceneName: string): string {
  for (const [keywords, title] of SCENE_TITLE_MAP) {
    for (const kw of keywords) {
      if (sceneName.includes(kw)) return title;
    }
  }
  return '任务清单';
}

// ═══ TM 收敛结果卡片 — 按父级分组的叶子列表 ═══
function TMResultsCard() {
  const thinkingMap = useStore(s => s.thinkingMap);
  const currentScene = useStore(s => s.currentScene);
  const nodes: any[] = thinkingMap?.nodes || [];
  const sceneName = currentScene?.name || '';
  const panelTitle = guessPanelTitle(sceneName);

  // 找出所有叶子节点（不被任何其他节点引用的节点）
  const leafIds = new Set(
    nodes.filter((n: any) => {
      if (n.type === 'root') return false;
      return !nodes.some(c => c.parent_id === n.id);
    }).map((n: any) => n.id)
  );

  // 按 parent_id 分组的叶子
  const groupMap = new Map<string, { parentId: string; parentLabel: string; leaves: any[]; status: string }>();


  nodes.filter((n: any) => leafIds.has(n.id)).forEach((leaf: any) => {
    const pid = leaf.parent_id || 'ungrouped';
    const parentNode = pid !== 'ungrouped' ? nodes.find((n: any) => n.id === pid) : null;
    if (!groupMap.has(pid)) {
      groupMap.set(pid, {
        parentId: pid,
        parentLabel: parentNode?.label || (pid === 'ungrouped' ? '其他' : pid),
        leaves: [],
        status: parentNode?.status || 'active',
      });
    }
    groupMap.get(pid)!.leaves.push(leaf);
  });

  // 按 parent 在树中的顺序排序（大致维持原始顺序）
  const groups = [...groupMap.values()].sort((a, b) => {
    const aIdx = nodes.findIndex((n: any) => n.id === a.parentId);
    const bIdx = nodes.findIndex((n: any) => n.id === b.parentId);
    return aIdx - bIdx;
  });

  // 废弃/反馈注入的单独显示（不分组）
  const discardedLeafIds = new Set(
    nodes.filter((n: any) => leafIds.has(n.id) && n.status === 'discarded').map((n: any) => n.id)
  );
  const feedbackLeafIds = new Set(
    nodes.filter((n: any) => leafIds.has(n.id) && n.created_by === 'reflect').map((n: any) => n.id)
  );

  return (
    <div className="card">
      <h3>📋 {panelTitle} <span className="badge badge-orange">叶子汇总</span></h3>
      <div className="tm-nodes">
        {groups.length === 0 ? (
          <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
            发送消息后自动生成
          </div>
        ) : (
          groups.map((group) => {
            if (group.leaves.length === 0) return null;
            return <GroupSection key={group.parentId} group={group} allNodes={nodes} />;
          })
        )}
        {/* 挂单的废弃/反馈叶子 — 只在未归组时显示 */}
        {(() => {
          const orphans = nodes.filter((n: any) =>
            leafIds.has(n.id) && (n.status === 'discarded' || n.created_by === 'reflect')
            && !groups.some(g => g.leaves.some(l => l.id === n.id))
          );
          if (orphans.length === 0) return null;
          return <GroupSection key="orphan" group={{
            parentId: 'orphan',
            parentLabel: '其他',
            leaves: orphans,
            status: 'active',
          }} allNodes={nodes} />;
        })()}
      </div>
    </div>
  );
}

function getGroupDominantStatus(leaves: any[]): string {
  // 按优先级决定组的整体色调
  const counts: Record<string, number> = {};
  for (const l of leaves) {
    const key = l.created_by === 'reflect' ? 'reflect' : l.status === 'discarded' ? 'discarded' : l.status === 'confirmed' && l.converged_from?.length ? 'converged' : l.priority ? 'queued' : 'brainstorm';
    counts[key] = (counts[key] || 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'brainstorm';
}

const GROUP_STYLES: Record<string, { border: string; bg: string; accent: string }> = {
  converged: { border: 'rgba(249,115,22,0.3)', bg: 'rgba(249,115,22,0.06)', accent: '#fb923c' },
  queued:    { border: 'rgba(34,197,94,0.3)', bg: 'rgba(34,197,94,0.06)', accent: '#4ade80' },
  brainstorm:{ border: 'rgba(59,130,246,0.3)', bg: 'rgba(59,130,246,0.06)', accent: '#60a5fa' },
  reflect:   { border: 'rgba(236,72,153,0.3)', bg: 'rgba(236,72,153,0.06)', accent: '#f472b6' },
  discarded: { border: 'rgba(239,68,68,0.3)', bg: 'rgba(239,68,68,0.04)', accent: '#f87171' },
};

const LEAF_STATUS = {
  reflect:    { bg: 'rgba(236,72,153,0.08)', border: 'rgba(236,72,153,0.25)', color: '#f472b6', badge: '💡 反馈', badgeBg: 'rgba(236,72,153,0.12)' },
  converged:  { bg: 'rgba(249,115,22,0.08)', border: 'rgba(249,115,22,0.25)', color: '#fb923c', badge: '🔀 合并', badgeBg: 'rgba(249,115,22,0.12)' },
  queued:     { bg: 'rgba(34,197,94,0.08)',  border: 'rgba(34,197,94,0.25)',  color: '#4ade80', badge: '→队列', badgeBg: 'rgba(34,197,94,0.12)' },
  brainstorm: { bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.25)', color: '#60a5fa', badge: '头脑风暴', badgeBg: 'rgba(59,130,246,0.12)' },
  discarded:  { bg: 'rgba(239,68,68,0.04)',  border: 'rgba(239,68,68,0.15)',  color: '#888',   badge: '已废弃', badgeBg: 'rgba(239,68,68,0.08)' },
};

function getLeafStatus(leaf: any): 'reflect' | 'discarded' | 'converged' | 'queued' | 'brainstorm' {
  if (leaf.created_by === 'reflect') return 'reflect';
  if (leaf.status === 'discarded') return 'discarded';
  if (leaf.status === 'confirmed' && leaf.converged_from?.length > 0) return 'converged';
  if (leaf.priority) return 'queued';
  return 'brainstorm';
}

function GroupSection({ group, allNodes }: { group: { parentId: string; parentLabel: string; leaves: any[]; status: string }; allNodes: any[] }) {
  const [expanded, setExpanded] = useState(true);
  const [popupLeaf, setPopupLeaf] = useState<any | null>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const dominant = getGroupDominantStatus(group.leaves);
  const gs = GROUP_STYLES[dominant] || GROUP_STYLES.brainstorm;

  // Close popover on click outside
  useEffect(() => {
    if (!popupLeaf) return;
    const handler = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setPopupLeaf(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [popupLeaf]);

  return (
    <div className="tm-group" style={{ border: `1px solid ${gs.border}`, background: gs.bg }}>
      <div className="tm-group-header" style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setExpanded(v => !v)}>
        <span className="collapse-arrow">{expanded ? '▼' : '▶'}</span>
        <strong className="group-label">{group.parentLabel}</strong>
        <span className="badge" style={{
          background: gs.bg, color: gs.accent, fontSize: 11,
          padding: '1px 7px', borderRadius: 8, border: `1px solid ${gs.border}`,
        }}>{group.leaves.length}</span>
      </div>
      {expanded && (
        <div className="tm-group-leaves">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px 8px', padding: '4px 0' }}>
            {group.leaves.map((leaf: any) => {
              const ls = LEAF_STATUS[getLeafStatus(leaf)] || LEAF_STATUS.brainstorm;
              return (
                <span key={leaf.id} className="tm-leaf-chip" style={{
                  background: ls.bg, border: `1px solid ${ls.border}`,
                  textDecoration: leaf.status === 'discarded' ? 'line-through' : 'none',
                  opacity: leaf.status === 'discarded' ? 0.5 : 1,
                  cursor: 'pointer', position: 'relative',
                }}
                  onClick={(e) => { e.stopPropagation(); setPopupLeaf(leaf); }}>
                  {leaf.label}
                  <span className="leaf-badge" style={{
                    fontSize: 9, padding: '0 5px', borderRadius: 3,
                    background: ls.badgeBg, color: ls.color, marginLeft: 3,
                    whiteSpace: 'nowrap',
                  }}>{ls.badge}{leaf.priority ? ` P${leaf.priority}` : ''}</span>

                  {/* Detail popover */}
                  {popupLeaf?.id === leaf.id && (
                    <div ref={popupRef}
                      style={{
                        position: 'absolute', top: '100%', left: 0, zIndex: 100,
                        background: '#1e1e2e', border: '1px solid #444', borderRadius: 8,
                        padding: '10px 14px', minWidth: 180, maxWidth: 260,
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                        fontSize: 12, color: '#ccc', marginTop: 4,
                      }}
                      onClick={e => e.stopPropagation()}>
                      <div style={{ fontWeight: 600, color: '#e6edf3', marginBottom: 6, fontSize: 13 }}>
                        {leaf.label}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <div><span style={{ color: '#888' }}>状态: </span><span style={{ color: ls.color }}>{leaf.status || 'active'}</span></div>
                        {leaf.priority && <div><span style={{ color: '#888' }}>优先级: </span><span style={{ color: '#fb923c' }}>P{leaf.priority}</span></div>}
                        <div><span style={{ color: '#888' }}>创建者: </span><span>{leaf.created_by || 'brainstorm'}</span></div>
                        {leaf.converged_from?.length > 0 && (
                          <div><span style={{ color: '#888' }}>合并自: </span><span style={{ color: '#fb923c' }}>{leaf.converged_from.length} 项</span></div>
                        )}
                      </div>
                    </div>
                  )}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══ Priority Queue 卡片 ═══
function PriorityQueueCard() {
  const pq = useStore(s => s.priorityQueue);
  const [wipLimit, setWipLimit] = useState<number>(() => {
    const saved = localStorage.getItem('pq-wip-limit');
    return saved ? Number(saved) : 3;
  });
  const [localItems, setLocalItems] = useState<DashboardQueueItem[]>([]);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const dragItemRef = useRef<number | null>(null);

  // Sync local items from store — add new items, keep local overrides for existing
  useEffect(() => {
    setLocalItems(prev => {
      if (prev.length === 0 && pq.length > 0) return [...pq];
      const existingIds = new Set(prev.map(i => i.id));
      const newItems = pq.filter(i => !existingIds.has(i.id));
      if (newItems.length > 0) return [...prev, ...newItems];
      return prev;
    });
  }, [pq]);

  const items = localItems.length > 0 ? localItems : pq;

  const running = items.filter(i => i.status === 'running');
  const pending = items.filter(i => i.status === 'pending');
  const completed = items.filter(i => i.status === 'completed');
  const blocked = items.filter(i => i.status === 'blocked');

  const priorityColor = (p: number) => {
    const map: Record<number, string> = { 1: '#f87171', 2: '#fb923c', 3: '#60a5fa', 4: '#888' };
    return map[p] || '#888';
  };
  const priorityBg = (p: number) => {
    const map: Record<number, string> = { 1: 'rgba(239,68,68,0.2)', 2: 'rgba(249,115,22,0.2)', 3: 'rgba(59,130,246,0.2)', 4: 'rgba(100,100,120,0.2)' };
    return map[p] || 'rgba(100,100,120,0.2)';
  };

  const all = [...running, ...pending, ...blocked, ...completed];

  const handleWipChange = (val: number) => {
    const clamped = Math.max(1, Math.min(5, Number(val) || 1));
    setWipLimit(clamped);
    localStorage.setItem('pq-wip-limit', String(clamped));
  };

  // --- Drag & Drop ---
  const handleDragStart = (idx: number) => {
    dragItemRef.current = idx;
  };

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setDragOverIdx(idx);
  };

  const handleDrop = (idx: number) => {
    const from = dragItemRef.current;
    if (from === null || from === idx) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(idx, 0, moved);
    setLocalItems(next);
    dragItemRef.current = null;
    setDragOverIdx(null);
  };

  const handleDragEnd = () => {
    dragItemRef.current = null;
    setDragOverIdx(null);
  };

  // --- Status toggle ---
  const updateItemStatus = async (itemId: string, newStatus: string) => {
    try {
      await fetch(`/api/priority-queues/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
    } catch {
      // API 不存在，只更新本地 state
    }
    setLocalItems(prev => prev.map(i => i.id === itemId ? { ...i, status: newStatus } : i));
  };

  const statusBtnStyle = (active: boolean) => ({
    fontSize: 12,
    padding: '1px 5px',
    borderRadius: 4,
    border: active ? '1px solid rgba(139,92,246,0.5)' : '1px solid transparent',
    background: active ? 'rgba(139,92,246,0.2)' : 'transparent',
    color: active ? '#c084fc' : '#666',
    cursor: 'pointer',
    lineHeight: '1.4',
    transition: 'all 0.15s',
  });

  return (
    <div className="card">
      <h3>📊 Priority Queue <span className="badge badge-purple">DAG + 拓扑排序</span></h3>

      {/* WIP 限制 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
        fontSize: 12, color: '#a78bfa',
      }}>
        <span>WIP 限制:</span>
        <input type="number" min={1} max={5} value={wipLimit}
          onChange={e => handleWipChange(Number(e.target.value))}
          style={{
            width: 48, padding: '2px 6px', borderRadius: 4, border: '1px solid rgba(139,92,246,0.3)',
            background: 'rgba(139,92,246,0.08)', color: '#c084fc', fontSize: 12, textAlign: 'center',
          }} />
        <span style={{ color: '#666' }}>/ 5</span>
      </div>

      {all.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          收敛后自动生成优先级队列
        </div>
      ) : (
        all.map((item, i) => {
          const isDragOver = dragOverIdx === i;
          const isDragging = dragItemRef.current === i;
          return (
            <div key={item.id}
              draggable
              onDragStart={() => handleDragStart(i)}
              onDragOver={e => handleDragOver(e, i)}
              onDrop={() => handleDrop(i)}
              onDragEnd={handleDragEnd}
              className={`pq-item ${item.status === 'running' ? 'active' : ''} ${item.status === 'completed' ? 'completed' : ''}`}
              style={{
                opacity: isDragging ? 0.4 : 1,
                border: isDragOver ? '1px dashed rgba(139,92,246,0.6)' : undefined,
                cursor: 'grab',
                transition: 'opacity 0.15s, border 0.15s',
              }}>
              <span className={`prio p${item.priority}`} style={{
                background: priorityBg(item.priority), color: priorityColor(item.priority),
              }}>P{item.priority}</span>
              <span className="pq-text">
                {item.title}
                {item.deps && item.deps.length > 0 && (
                  <span className="dep">依赖: {item.deps.join(', ')} · {item.status === 'running' ? '执行中' : item.status === 'blocked' ? '阻塞' : ''}</span>
                )}
              </span>
              <span style={{ display: 'flex', gap: 3, marginLeft: 'auto', flexShrink: 0 }}>
                <button onClick={e => { e.stopPropagation(); updateItemStatus(item.id, 'running'); }}
                  style={statusBtnStyle(item.status === 'running')}
                  title="设为执行中">▶</button>
                <button onClick={e => { e.stopPropagation(); updateItemStatus(item.id, 'blocked'); }}
                  style={statusBtnStyle(item.status === 'blocked')}
                  title="设为阻塞">⏸</button>
                <button onClick={e => { e.stopPropagation(); updateItemStatus(item.id, 'completed'); }}
                  style={statusBtnStyle(item.status === 'completed')}
                  title="设为完成">✅</button>
              </span>
            </div>
          );
        })
      )}
      {all.length > 0 && (
        <div className="pq-status">
          <span>📋 队列中: <strong>{pending.length + running.length}</strong></span>
          {blocked.length > 0 && <span>🔴 阻塞: <strong>{blocked.length}</strong></span>}
          <span>✅ 已完成: <strong>{completed.length}</strong></span>
        </div>
      )}
    </div>
  );
}

// ═══ Action Map 聚焦卡片 ═══
function ActionMapCard() {
  const pq = useStore(s => s.priorityQueue);
  const running = pq.filter(i => i.status === 'running');
  const pending = pq.filter(i => i.status === 'pending');
  const completed = pq.filter(i => i.status === 'completed');
  const activeTask = running[0] || null;
  const nextUp = pending.slice(0, 3);

  return (
    <div className="card">
      <h3>🎯 Action Map <span className="badge badge-green">聚焦执行</span></h3>
      <div className="am-focus">
        {activeTask ? (
          <div className="am-active-card">
            <div className="am-label">▶ 当前执行</div>
            <h4>{activeTask.title}</h4>
            <div className="am-progress">
              <div className="am-progress-bar" style={{ width: '45%' }}></div>
            </div>
          </div>
        ) : (
          <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
            {completed.length > 0 ? '✅ 所有任务已完成' : '等待执行任务...'}
          </div>
        )}
        {nextUp.length > 0 && (
          <div className="am-queue-preview">
            <div className="am-queue-item">
              <span className="q-dot" style={{ background: '#fb923c' }}></span>
              <span className="q-text">⬆ 下一步: {nextUp[0].title}</span>
            </div>
            {nextUp.slice(1).map((item, i) => (
              <div key={item.id} className="am-queue-item">
                <span className="q-dot"></span>
                <span className="q-text">{i + 2}. {item.title}</span>
              </div>
            ))}
          </div>
        )}
        {completed.length > 0 && (
          <div className="am-completed">
            <div className="am-c-label">▼ 已完成 ({completed.length})</div>
            <div className="am-completed-item">✅ {completed[completed.length - 1].title}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══ Reflect Timeline 卡片 ═══
function ReflectCard() {
  const reflectTimeline = useStore(s => s.reflectTimeline);
  const [displayCount, setDisplayCount] = useState(10);
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const filterOptions = [
    { key: 'all', label: '全部' },
    { key: 'success', label: '✅ 成功' },
    { key: 'fail', label: '🔴 失败' },
    { key: 'new', label: '💡 新发现' },
  ];

  const filtered = typeFilter === 'all'
    ? reflectTimeline
    : reflectTimeline.filter(i => i.type === typeFilter);

  const reversed = [...filtered].reverse();
  const visible = reversed.slice(0, displayCount);
  const hasMore = displayCount < filtered.length && displayCount < 50;

  const loadMore = () => {
    setDisplayCount(prev => Math.min(prev + 10, 50, filtered.length));
  };

  return (
    <div className="card">
      <h3>🔄 Reflect Timeline <span className="badge badge-pink">反馈调整</span></h3>

      {/* 类型过滤 */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
        {filterOptions.map(opt => (
          <button key={opt.key} onClick={() => { setTypeFilter(opt.key); setDisplayCount(10); }}
            style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 10, border: 'none',
              background: typeFilter === opt.key ? 'rgba(236,72,153,0.2)' : 'rgba(60,60,80,0.3)',
              color: typeFilter === opt.key ? '#f472b6' : '#888',
              cursor: 'pointer', transition: 'all 0.15s',
            }}>
            {opt.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          工具执行后将在此记录
        </div>
      ) : (
        <>
          {visible.map((item: DashboardReflectItem) => (
            <div key={item.id} className="reflect-item">
              <div className={`r-icon ${item.type === 'success' ? 'success' : item.type === 'fail' ? 'fail' : 'new'}`}>
                {item.icon || (item.type === 'success' ? '✅' : item.type === 'fail' ? '🔴' : '💡')}
              </div>
              <div className="r-content">
                <div className="r-title">{item.title}</div>
                {item.detail && <div className="r-detail">{item.detail.slice(0, 120)}</div>}
                {item.tag === 'inject' && <span className="r-tag inject">↪ {item.tag_text || '注入TM'}</span>}
                {item.tag === 'blocked' && <span className="r-tag blocked">🚫 {item.tag_text || '阻塞'}</span>}
              </div>
            </div>
          ))}
          {hasMore && (
            <button onClick={loadMore}
              style={{
                display: 'block', width: '100%', marginTop: 8, padding: '6px 0',
                background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)',
                color: '#a78bfa', borderRadius: 6, cursor: 'pointer', fontSize: 12,
                textAlign: 'center',
              }}>
              加载更多 ({displayCount}/{Math.min(filtered.length, 50)})
            </button>
          )}
          {filtered.length > 50 && displayCount >= 50 && (
            <div style={{ fontSize: 11, color: '#666', textAlign: 'center', marginTop: 6 }}>
              最多显示 50 条
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══ Status Bar ═══
const PHASE_LABELS: Record<string, string> = {
  diverge: '🧠 发散', converge: '🔀 收敛', sort: '📊 排序',
  focus: '🎯 聚焦', reflect: '🔄 反馈',
};

function DashboardStatusBar() {
  const { dashboardPhase, dashboardLoopCount, dashboardStepCount, contextUsage, currentModelName } = useStore();

  return (
    <div className="dashboard-status-bar">
      <span className="dot-active"></span>
      <span>Agent Loop 运行中</span>
      <span>|</span>
      <span>当前阶段: <strong>{PHASE_LABELS[dashboardPhase] || dashboardPhase}</strong></span>
      <span>|</span>
      <span>循环: {dashboardLoopCount}</span>
      <span>|</span>
      <span>步: {dashboardStepCount}</span>
      {contextUsage && (
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>
          ⚡ Token: {contextUsage.usageStr} · {contextUsage.progressBar}
        </span>
      )}
    </div>
  );
}

// ═══ 仪表盘根组件 ═══
export default function AgentLoopDashboard() {
  return (
    <div className="agent-loop-dashboard">
      <LoopDiagram />
      <CollapsibleMindMap />
      <div className="grid dashboard-grid">
        <TMResultsCard />
        <PriorityQueueCard />
        <ActionMapCard />
        <ReflectCard />
      </div>
      <DashboardStatusBar />
    </div>
  );
}

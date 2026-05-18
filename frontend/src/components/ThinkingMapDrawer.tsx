import { useState } from 'react';
import { useStore } from '../stores/appStore';
import { CustomMindMap, type ThinkNodeData, type MergeRecord } from './CustomMindMap';

export function ThinkingMapDrawer() {
  const { drawerOpen, closeDrawer, thinkingMap, toggleNodeActionable,
    convergeThinkingMap, prioritizeThinkingMap, getPriorityQueue } = useStore();
  const [showNodeSettings, setShowNodeSettings] = useState(false);
  const [converging, setConverging] = useState(false);
  const [convergeResult, setConvergeResult] = useState<any>(null);
  const [queueData, setQueueData] = useState<any[] | null>(null);
  const [showQueue, setShowQueue] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);

  if (!drawerOpen) return null;

  const nodes = thinkingMap?.nodes || [];
  const mapId = thinkingMap?.id;

  // ── 转换 API ThinkNode[] → CustomMindMap ThinkNodeData[] ──
  const mindMapNodes: ThinkNodeData[] = nodes.map((n: any) => ({
    id: n.id,
    parent_id: n.parent_id || null,
    label: n.label,
    status: n.status,
    created_by: n.created_by || 'brainstorm',
    action_status: n.action_status || null,
    converged_from: n.converged_from || [],
  }));

  // ── 从 converged_from 构建 MergeRecord[] ──
  const mergeRecords: MergeRecord[] = [];
  const usedMerges = new Set<string>();
  for (const n of mindMapNodes) {
    if (n.converged_from && n.converged_from.length > 0 && !usedMerges.has(n.id)) {
      usedMerges.add(n.id);
      mergeRecords.push({
        target_node_id: n.id,
        source_labels: n.converged_from,
      });
    }
  }
  // 如果有实时 convergeResult，附加到前面（新数据优先）
  if (convergeResult && convergeResult.length > 0) {
    const liveMerges: MergeRecord[] = convergeResult.map((m: any) => ({
      target_node_id: m.target_id,
      source_labels: m.source_labels,
    }));
    mergeRecords.unshift(...liveMerges);
  }

  // 找所有叶子节点（用于节点设置面板）
  const leafNodes = nodes.filter(
    (n: any) => n.type === 'leaf' && !nodes.some((c: any) => c.parent_id === n.id)
  );

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(prev => prev === nodeId ? null : nodeId);
    // 如果节点设置面板没开，自动打开
    if (!showNodeSettings) {
      setShowNodeSettings(true);
      setShowQueue(false);
    }
  };

  const selectedNode = selectedNodeId ? nodes.find((n: any) => n.id === selectedNodeId) : null;

  const handleConverge = async () => {
    if (!mapId) return;
    setConverging(true);
    try {
      const r = await convergeThinkingMap();
      setConvergeResult(r?.merged || []);
      const q = await prioritizeThinkingMap();
      if (q?.queue) setQueueData(q.queue);
    } finally {
      setConverging(false);
    }
  };

  const loadQueue = async () => {
    if (!mapId) return;
    setQueueLoading(true);
    try {
      const q = await getPriorityQueue();
      if (q?.queue) setQueueData(q.queue);
    } finally {
      setQueueLoading(false);
    }
  };

  return (
    <>
      <div className="drawer-overlay open" onClick={closeDrawer} />
      <div className="drawer open">
        <div className="drawer-header">
          <span className="tab active">🧠 Thinking Map</span>
          <button
            className={`tab ${showNodeSettings ? 'active' : ''}`}
            style={{
              cursor: 'pointer', border: 'none', background: 'none',
              color: showNodeSettings ? '#58a6ff' : '#8b949e',
              fontSize: '14px', padding: '4px 12px',
            }}
            onClick={() => { setShowNodeSettings(!showNodeSettings); setShowQueue(false); }}
          >
            🔧 节点设置
          </button>
          <button
            className={`tab ${showQueue ? 'active' : ''}`}
            style={{
              cursor: 'pointer', border: 'none', background: 'none',
              color: showQueue ? '#58a6ff' : '#8b949e',
              fontSize: '14px', padding: '4px 12px',
            }}
            onClick={() => {
              if (!showQueue) loadQueue();
              setShowQueue(!showQueue);
              setShowNodeSettings(false);
            }}
          >
            📊 队列
          </button>
          <span className="close" onClick={closeDrawer}>✕</span>
        </div>
        <div className="drawer-body" style={{
          background: '#0d1117', display: 'flex', flexDirection: 'column',
          padding: 0, overflow: 'hidden',
        }}>
          {/* ── 自定义思维导图 ── */}
          {nodes.length > 0 ? (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <CustomMindMap
                nodes={mindMapNodes}
                merges={mergeRecords}
                onNodeClick={handleNodeClick}
                height={showNodeSettings || showQueue ? 300 : undefined}
              />
            </div>
          ) : (
            <div style={{
              flex: 1, minHeight: 0, display: 'flex', alignItems: 'center',
              justifyContent: 'center', color: '#8b949e', fontSize: 14,
            }}>
              暂无思维导图数据
            </div>
          )}

          {/* ── 选中节点详情 ── */}
          {selectedNode && showNodeSettings && (
            <div style={{
              padding: '10px 16px', margin: '0 12px 8px',
              background: '#161b22', borderRadius: 8, fontSize: 12,
            }}>
              <div style={{ color: '#e6edf3', fontWeight: 600, marginBottom: 4 }}>
                {selectedNode.label}
              </div>
              <div style={{ color: '#8b949e', lineHeight: 1.6 }}>
                状态: {selectedNode.status}
                {selectedNode.created_by && ` · 来源: ${selectedNode.created_by}`}
                {selectedNode.action_status && ` · 执行: ${selectedNode.action_status}`}
              </div>
            </div>
          )}

          {/* ═══ 节点设置面板 ═══ */}
          {showNodeSettings && (
            <div className="node-settings-panel">
              <h4 style={{ margin: '0 0 8px', fontSize: '14px', color: '#e6edf3' }}>
                🔧 叶子节点设置
              </h4>
              <p style={{ fontSize: '12px', color: '#8b949e', margin: '0 0 12px' }}>
                标记「可执行」后，可在 ⚡ Action Map 抽屉中生成行动计划
              </p>
              {leafNodes.length === 0 ? (
                <div style={{ color: '#8b949e', fontSize: '13px', padding: '12px 0', textAlign: 'center' }}>
                  暂无叶子节点
                </div>
              ) : (
                <div className="node-settings-list">
                  {leafNodes.map((n: any) => (
                    <div key={n.id} className="node-settings-row">
                      <div className="node-settings-info">
                        <span className="node-settings-label">
                          {n.actionable && '🔧 '}
                          {n.label}
                        </span>
                        <span className="node-settings-status">
                          {n.status === 'confirmed' ? '✅' : n.status === 'discussing' ? '❓' : ''}
                        </span>
                      </div>
                      <button
                        className={`toggle-actionable ${n.actionable ? 'on' : 'off'}`}
                        onClick={() => toggleNodeActionable(n.id, !n.actionable)}
                      >
                        {n.actionable ? '🔧 可执行' : '○ 设为可执行'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ═══ 收敛 + 队列面板 ═══ */}
          {showQueue && (
            <div className="node-settings-panel" style={{ borderTop: '1px solid #21262d' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                <button
                  disabled={converging}
                  style={{
                    padding: '6px 14px', borderRadius: 6, border: '1px solid #f97316',
                    background: converging ? '#1a1a24' : 'rgba(249,115,22,0.12)',
                    color: converging ? '#555' : '#fb923c',
                    cursor: converging ? 'default' : 'pointer',
                    fontSize: 12, fontWeight: 500,
                  }}
                  onClick={handleConverge}
                >
                  {converging ? '⏳ 收敛中...' : '🔀 收敛并排序'}
                </button>
                <button
                  onClick={loadQueue}
                  disabled={queueLoading}
                  style={{
                    padding: '6px 14px', borderRadius: 6, border: '1px solid #30363d',
                    background: 'transparent',
                    color: '#8b949e', cursor: queueLoading ? 'default' : 'pointer',
                    fontSize: 12,
                  }}
                >
                  {queueLoading ? '⏳' : '🔄 刷新'}
                </button>
              </div>

              {convergeResult && convergeResult.length > 0 && (
                <div style={{ fontSize: 12, color: '#fb923c', marginBottom: 8 }}>
                  ✅ 合并 {convergeResult.length} 组：
                  {convergeResult.map((m: any, i: number) => (
                    <div key={i} style={{
                      color: '#8b949e', fontSize: 11, marginTop: 4,
                      padding: '4px 8px', background: 'rgba(249,115,22,0.05)', borderRadius: 4,
                    }}>
                      🔀 {m.target_label} ← {m.source_labels.join(' + ')}
                    </div>
                  ))}
                </div>
              )}

              {queueData && queueData.length > 0 && (
                <>
                  <h4 style={{ margin: '8px 0', fontSize: 13, color: '#e6edf3' }}>📊 Priority Queue</h4>
                  {queueData.map((q: any) => {
                    const colors: Record<number, string> = { 1: '#f87171', 2: '#fb923c', 3: '#60a5fa' };
                    const bg: Record<number, string> = { 1: 'rgba(239,68,68,0.15)', 2: 'rgba(249,115,22,0.15)', 3: 'rgba(59,130,246,0.15)' };
                    const p = q.priority || 4;
                    return (
                      <div key={q.id} style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '6px 8px', marginBottom: 4,
                        background: '#161b22', borderRadius: 6, fontSize: 12,
                        cursor: 'pointer',
                        border: selectedNodeId === q.id ? '1px solid #58a6ff' : '1px solid transparent',
                      }}
                        onClick={() => handleNodeClick(q.id)}
                      >
                        <span style={{ color: '#555', width: 20, textAlign: 'center' }}>
                          #{q.queue_order}
                        </span>
                        <span style={{
                          padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                          background: bg[p] || 'rgba(100,100,120,0.15)',
                          color: colors[p] || '#888',
                        }}>
                          P{p}
                        </span>
                        <span style={{ flex: 1, color: '#e6edf3' }}>{q.label}</span>
                        {q.blocks_count > 0 && (
                          <span style={{ fontSize: 10, color: '#8b949e' }}>
                            🔗阻塞{q.blocks_count}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </>
              )}

              {queueData && queueData.length === 0 && (
                <div style={{ color: '#8b949e', fontSize: 12, padding: '8px 0' }}>
                  队列为空，点击「收敛并排序」生成
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

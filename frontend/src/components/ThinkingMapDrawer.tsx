import { useEffect, useRef, useState } from 'react';
import { useStore } from '../stores/appStore';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';

/** 扁平节点 → markdown */
function nodesToMarkdown(nodes: any[]): string {
  if (!nodes || nodes.length === 0) return '# 暂无数据';
  const root = nodes.find((n: any) => n.type === 'root' && !n.parent_id);
  if (!root) return '# 无根节点';
  const childrenMap: Record<string, any[]> = {};
  nodes.forEach(n => {
    const pid = n.parent_id || '__orphan__';
    if (!childrenMap[pid]) childrenMap[pid] = [];
    childrenMap[pid].push(n);
  });
  const walk = (nodeId: string, level: number): string => {
    const node = nodes.find((n: any) => n.id === nodeId);
    if (!node) return '';
    const prefix = '#'.repeat(Math.min(level + 1, 6));
    let icon = '';
    if (node.status === 'confirmed') icon = ' ✓';
    else if (node.status === 'discussing') icon = ' ❓';
    if (node.actionable) icon += ' 🔧';
    let md = `${prefix} ${node.label}${icon}\n`;
    const kids = childrenMap[node.id] || [];
    for (const kid of kids) kids.sort((a: any, b: any) => a.label.localeCompare(b.label));
    for (const kid of kids) md += walk(kid.id, level + 1);
    return md;
  };
  return walk(root.id, 0);
}

export function ThinkingMapDrawer() {
  const { drawerOpen, closeDrawer, thinkingMap, toggleNodeActionable,
    convergeThinkingMap, prioritizeThinkingMap, getPriorityQueue } = useStore();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [showNodeSettings, setShowNodeSettings] = useState(false);
  const [converging, setConverging] = useState(false);
  const [convergeResult, setConvergeResult] = useState<any>(null);
  const [queueData, setQueueData] = useState<any[] | null>(null);
  const [showQueue, setShowQueue] = useState(false);

  useEffect(() => {
    if (!drawerOpen || !thinkingMap) return;

    if (!wrapRef.current) return;
    setStatus('loading');

    const el = wrapRef.current;
    el.innerHTML = '';

    try {
      const markdown = nodesToMarkdown(thinkingMap.nodes);

      const transformer = new Transformer();
      const result = transformer.transform(markdown);

      if (!result?.root) {
        throw new Error('Transformer 返回了空数据');
      }

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      el.appendChild(svg);
      el.classList.add('markmap-dark');
      const mm = Markmap.create(svg, { duration: 0 }, result.root);
      mm.fit();
      setStatus('ready');
    } catch (e: any) {
      console.error('[ThinkingMap] render error:', e);
      setStatus('error');
      el.innerHTML = `<pre style="color:#f85149;padding:20px;font-size:12px">渲染失败: ${e.message}\n\n${nodesToMarkdown(thinkingMap.nodes)}</pre>`;
    }
  }, [drawerOpen, thinkingMap]);

  if (!drawerOpen) return null;

  // 找所有叶子节点
  const leafNodes = (thinkingMap?.nodes || []).filter(
    (n: any) => n.type === 'leaf' && !(thinkingMap?.nodes || []).some((c: any) => c.parent_id === n.id)
  );

  return (
    <>
      <div className="drawer-overlay open" onClick={closeDrawer} />
      <div className="drawer open">
        <div className="drawer-header">
          <span className="tab active">🧠 Thinking Map</span>
          <button
            className={`tab ${showNodeSettings ? 'active' : ''}`}
            style={{ cursor: 'pointer', border: 'none', background: 'none', color: showNodeSettings ? '#58a6ff' : '#8b949e', fontSize: '14px', padding: '4px 12px' }}
            onClick={() => setShowNodeSettings(!showNodeSettings)}
          >
            🔧 节点设置
          </button>
          <button
            className={`tab ${showQueue ? 'active' : ''}`}
            style={{ cursor: 'pointer', border: 'none', background: 'none', color: showQueue ? '#58a6ff' : '#8b949e', fontSize: '14px', padding: '4px 12px' }}
            onClick={async () => {
              if (!showQueue) {
                const q = await getPriorityQueue();
                if (q?.queue) setQueueData(q.queue);
              }
              setShowQueue(!showQueue);
              setShowNodeSettings(false);
            }}
          >
            📊 队列
          </button>
          <span className="close" onClick={closeDrawer}>✕</span>
        </div>
        <div className="drawer-body" style={{ background: '#0d1117', display: 'flex', flexDirection: 'column' }}>
          {status === 'loading' && (
            <div style={{ color: '#8b949e', padding: 40, textAlign: 'center' }}>加载中...</div>
          )}
          <div id="mindmap-wrap" ref={wrapRef} style={{ flex: 1, minHeight: 0 }} />

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
                    color: converging ? '#555' : '#fb923c', cursor: converging ? 'default' : 'pointer',
                    fontSize: 12, fontWeight: 500,
                  }}
                  onClick={async () => {
                    setConverging(true);
                    try {
                      const r = await convergeThinkingMap();
                      setConvergeResult(r?.merged || []);
                      const q = await prioritizeThinkingMap();
                      if (q?.queue) setQueueData(q.queue);
                    } finally {
                      setConverging(false);
                    }
                  }}
                >
                  {converging ? '⏳ 收敛中...' : '🔀 收敛并排序'}
                </button>
              </div>

              {convergeResult && convergeResult.length > 0 && (
                <div style={{ fontSize: 12, color: '#fb923c', marginBottom: 8 }}>
                  ✅ 合并 {convergeResult.length} 组：
                  {convergeResult.map((m: any, i: number) => (
                    <div key={i} style={{ color: '#8b949e', fontSize: 11, marginTop: 4, padding: '4px 8px', background: 'rgba(249,115,22,0.05)', borderRadius: 4 }}>
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
                      }}>
                        <span style={{ color: '#555', width: 20, textAlign: 'center' }}>#{q.queue_order}</span>
                        <span style={{
                          padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                          background: bg[p] || 'rgba(100,100,120,0.15)', color: colors[p] || '#888',
                        }}>P{p}</span>
                        <span style={{ flex: 1, color: '#e6edf3' }}>{q.label}</span>
                        {q.blocks_count > 0 && <span style={{ fontSize: 10, color: '#8b949e' }}>🔗阻塞{q.blocks_count}</span>}
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
